"""zdic.net lookup for Chinese characters and words — stdlib only.

Vendored implementation for the `zdic` plugin: it used to live in the host as
`yhub/cli/zdic.py`, which the host no longer ships. Plugins must be self-contained
(stdlib + host deps + `plugin_api` only), so the fetcher/parser lives here.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

from yhub.plugin_api import translator

# User-facing text lives in the plugin's own catalog (host registers it as `plugins.zdic.*`).
_t = translator("zdic")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36")
BASE = "https://zdic.net"


class ZdicError(Exception):
    """Plain-words error for the user; the adapter turns it into a ToolError for the frontend."""


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore"), r.geturl()


def text(html):
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"<[^>]*$", " ", s)  # the slice may cut mid-tag
    return re.sub(r"\s+", " ", unescape(s)).strip()


def meta_pairs(html):
    """Collect the <span class="meta-badge">label</span> / value pairs of every meta-row and word-pronun-row.

    Only slice inside each row container, so the rest of the page is never read as some label's value.
    """
    out, seen = [], set()
    rows = re.findall(r'<div class="(?:meta-row|word-pronun-row)"[^>]*>(.*?)</div>', html, re.S)
    for row in rows:
        marks = list(re.finditer(r'class="[^"]*meta-badge[^"]*"[^>]*>(.*?)</span>', row, re.S))
        for i, m in enumerate(marks):
            label = text(m.group(1))
            end = marks[i + 1].start() if i + 1 < len(marks) else len(row)
            value = text(row[m.end():end]).strip(" |")
            if not label or not value or len(value) > 80:
                continue
            if (label, value) not in seen:
                seen.add((label, value))
                out.append((label, value))
    return out


def defs(html):
    out = []
    for m in re.finditer(r'class="xxjs-item__def"[^>]*>(.*?)</div>', html, re.S):
        d = text(m.group(1))
        if d:
            out.append(d)
    if not out:  # detail-style page (single sense block)
        for m in re.finditer(r'class="xxjs-item__text"[^>]*>(.*?)</div>', html, re.S):
            d = text(m.group(1))
            if d:
                out.append(d)
    return out


def english(html):
    m = re.search(r'class="xxjs-english__text"[^>]*>(.*?)</span>', html, re.S)
    return text(m.group(1)) if m else ""


def search_links(html, limit=8):
    out, seen = [], set()
    for href, label in re.findall(r'href="(/(?:hans|hant|cy|ci)/[^"]+)"[^>]*>(.*?)</a>', html, re.S):
        name = text(label)
        if name and href not in seen:
            seen.add(href)
            out.append(name)
        if len(out) >= limit:
            break
    return out


def lookup(word: str, traditional: bool = False, links: bool = False) -> dict:
    """Look up one word and return a structured dict; raises ZdicError on failure."""
    word = (word or "").strip()
    if not word:
        raise ZdicError(_t("err.need_word"))

    path = "hant" if traditional else "hans"
    url = f"{BASE}/{path}/{urllib.parse.quote(word)}"
    try:
        html, final = fetch(url)
    except urllib.error.HTTPError as e:
        html, final = None, url
        if e.code != 404:
            raise ZdicError(_t("err.http", status=e.code)) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ZdicError(_t("err.network", reason=e)) from e

    if html is not None:
        pairs = meta_pairs(html)
        body = defs(html)
        title = re.search(r"<title>(.*?)</title>", html, re.S)
        if not pairs and not body:
            html = None
    result = {
        "word": word,
        "found": html is not None,
        "url": final if html is not None else url,
        "title": text(title.group(1)) if html is not None and title else "",
        "pinyin": "", "zhuyin": "", "meta": [], "definitions": [], "english": "",
        "source": "zdic.net",
    }
    if html is not None:
        for label, value in pairs:
            if label == "拼音":
                result["pinyin"] = result["pinyin"] or value
                result["meta"].append([label, value])
            elif label == "注音":
                result["zhuyin"] = value
                result["meta"].append([label, value])
            else:
                result["meta"].append([label, value])
        result["definitions"] = body
        result["english"] = english(html)
    if not result["found"] and links:
        try:
            sh, _ = fetch(f"{BASE}/search/?q={urllib.parse.quote(word)}")
            result["suggestions"] = search_links(sh)
        except Exception:
            result["suggestions"] = []
    return result


def render(r):
    """Human-readable CLI output. The `meta` labels come from the page itself (拼音 / 部首 / …), so
    they are data, not UI copy; everything we author goes through the catalog."""
    if not r["found"]:
        out = [_t("cli.not_found", word=r["word"]),
               _t("cli.try", url=f"{BASE}/search/?q={urllib.parse.quote(r['word'])}")]
        if r.get("suggestions"):
            out.append(_t("cli.search_results", items=" / ".join(r["suggestions"])))
        if r.get("error"):
            out.append(_t("cli.error", message=r["error"]))
        return "\n".join(out)
    lines = [f"[{r['word']}] {r['url']}"]
    for label, value in r["meta"]:
        lines.append(f"  {label:<4} {value}")
    if r["definitions"]:
        lines.append(_t("cli.definitions"))
        for i, d in enumerate(r["definitions"], 1):
            lines.append(f"   {i:>2}. {d}")
    if r["english"]:
        lines.append(_t("cli.english", text=r["english"]))
    return "\n".join(lines)


def stdin_words() -> list[str]:
    """Read stdin as a word list (split on whitespace). The adapter's CLI face and run() share this."""
    return [w for w in re.split(r"\s+", sys.stdin.read().strip()) if w]


def collect(words, traditional=False, links=False) -> tuple[list[dict], int]:
    """Look up a batch, returning (results, exit code). **Prints nothing**: the caller decides.

    One failed word does not blow up the batch: it becomes a found=False result and the exit code is 1.
    """
    results, code = [], 0
    for w in words:
        try:
            results.append(lookup(w, traditional, links))
        except Exception as e:
            results.append({"word": w, "found": False, "error": str(e), "url": "", "meta": [],
                            "definitions": [], "english": "", "title": "", "pinyin": "", "zhuyin": "",
                            "source": "zdic.net"})
            code = 1
    if not all(r["found"] for r in results):
        code = code or 1
    return results, code


def run(words, traditional=False, as_json=False, links=False) -> int:
    """Look up and print; empty words reads stdin. Returns the process exit code."""
    if not words:
        words = stdin_words()
    if not words:
        print(__doc__)
        return 2
    results, code = collect(words, traditional, links)
    if as_json:
        print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2))
    else:
        print("\n".join(render(r) for r in results))
    return code
