#!/usr/bin/env python3
"""Check registry.json against itself, against this repo, and (optionally) against the network.

The registry is the marketplace index the host fetches by default, so a wrong entry is not a
cosmetic bug: it decides what `yhub plugin install <id>` downloads and which Y-Hub versions it
claims to need. Three layers:

1. **shape** — schema 1, unique ids, one source per entry (`repo` | `archive`), `id` matching the
   manifest rules, bilingual name/description present, and a `ref` so an install by id is pinned:
   a plugin in this repository is tagged `<plugin-id>-v<version>` (one repository, two release
   lines), a standalone repository uses its own tag.
2. **local drift** — an entry with `subdir` lives in this repository, so its `version`, `min_yhub`
   and `ref` must match that plugin's own `plugin.json` and the tag convention. Catches
   "released 0.1.3, forgot the index".
3. **remote drift** (`--network`) — standalone entries (`repo` without `subdir`) are checked against
   `plugin.json` at the pinned `ref`, so a tag bump without a registry edit fails here instead of
   silently shipping an install that refuses to load.

Usage:
    python3 scripts/verify-registry.py            # shape + local drift (no network)
    python3 scripts/verify-registry.py --network  # also fetch every standalone entry
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry.json"
ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

failures: list[str] = []
checked = 0


def fail(message: str) -> None:
    failures.append(message)
    print(f"FAIL  {message}")


def ok(message: str) -> None:
    print(f"PASS  {message}")


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_manifest(repo: str, ref: str) -> tuple[dict | None, str]:
    """`plugin.json` at `<repo>@<ref>` (ref empty = default branch). Returns (manifest, raw_url)."""
    ref = ref or "main"
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/plugin.json"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310 — fixed https host
            return json.loads(resp.read().decode("utf-8")), url
    except Exception as exc:  # noqa: BLE001 — the message is the point
        return None, f"{url} ({exc})"


def main() -> int:
    global checked
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))

    if data.get("schema") != 1:
        fail(f"registry.json: schema is {data.get('schema')!r}, expected 1")
    else:
        ok("registry.json: schema 1")

    plugins = data.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        fail("registry.json: plugins is missing or empty")
        return 1

    ids = [p.get("id") for p in plugins if isinstance(p, dict)]
    dupes = {str(i) for i in ids if i and ids.count(i) > 1}
    if dupes:
        fail(f"registry.json: duplicate ids {sorted(dupes)}")
    else:
        ok(f"registry.json: {len(ids)} entries, ids unique")

    for entry in plugins:
        if not isinstance(entry, dict):
            fail(f"registry.json: non-object entry {entry!r}")
            continue
        pid = str(entry.get("id") or "")
        where = f"{pid or '<no id>'}"

        if not ID_RE.match(pid):
            fail(f"{where}: id must be lowercase-with-hyphens")
            continue
        if not (entry.get("repo") or entry.get("archive")):
            fail(f"{where}: needs `repo` or `archive`")
            continue
        if entry.get("pypi"):
            fail(f"{where}: `pypi` entries are rejected — PyPI is not a plugin source")
        if entry.get("repo") and not REPO_RE.match(str(entry["repo"])):
            fail(f"{where}: repo must be `owner/name`, got {entry['repo']!r}")
        version = str(entry.get("version") or "")
        if not VERSION_RE.match(version):
            fail(f"{where}: version must be x.y.z, got {version!r}")
        if not VERSION_RE.match(str(entry.get("min_yhub") or "")):
            fail(f"{where}: min_yhub must be x.y.z, got {entry.get('min_yhub')!r}")
        if not str(entry.get("description") or "").strip():
            fail(f"{where}: description is required (name_zh/description_zh feed the Chinese UI)")
        if not str(entry.get("name_zh") or "").strip() or not str(entry.get("description_zh") or "").strip():
            fail(f"{where}: name_zh and description_zh are required — the index is fetched before any locale exists")
        ref = str(entry.get("ref") or "")
        if not ref:
            fail(f"{where}: needs `ref` (a tag) — an unpinned entry downloads whatever the default branch is today")
        elif entry.get("subdir") and ref != f"{pid}-v{version}":
            fail(f"{where}: ref {ref!r} ≠ tag {pid}-v{version} — plugins in this repository are tagged <id>-v<version>")
        checked += 1

    # ---- local drift: entries that live in this repository
    for entry in plugins:
        subdir = str(entry.get("subdir") or "")
        if not subdir:
            continue
        manifest = ROOT / subdir / "plugin.json"
        if not manifest.is_file():
            fail(f"{entry['id']}: subdir {subdir!r} has no plugin.json")
            continue
        m = read_manifest(manifest)
        if m.get("id") != entry["id"]:
            fail(f"{entry['id']}: {subdir}/plugin.json declares id {m.get('id')!r}")
        if m.get("version") != entry["version"]:
            fail(f"{entry['id']}: registry version {entry['version']} ≠ {subdir}/plugin.json {m.get('version')}")
        if m.get("min_yhub") != entry["min_yhub"]:
            fail(f"{entry['id']}: registry min_yhub {entry['min_yhub']} ≠ {subdir}/plugin.json {m.get('min_yhub')}")
        ok(f"{entry['id']}: matches {subdir}/plugin.json ({entry['version']}, yhub ≥ {entry['min_yhub']})")

    # ---- remote drift: standalone repositories (opt-in, needs the network)
    if "--network" in sys.argv:
        for entry in plugins:
            if entry.get("subdir") or not entry.get("repo"):
                continue
            manifest, raw = fetch_manifest(str(entry["repo"]), str(entry.get("ref") or ""))
            if manifest is None:
                fail(f"{entry['id']}: cannot read {raw}")
                continue
            problems = []
            if manifest.get("version") != entry["version"]:
                problems.append(f"version {entry['version']} ≠ {manifest.get('version')}")
            if manifest.get("min_yhub") != entry["min_yhub"]:
                problems.append(f"min_yhub {entry['min_yhub']} ≠ {manifest.get('min_yhub')}")
            if manifest.get("id") != entry["id"]:
                problems.append(f"id {entry['id']} ≠ {manifest.get('id')}")
            if problems:
                fail(f"{entry['id']}: {entry['repo']}@{entry.get('ref') or 'HEAD'} — {'; '.join(problems)}")
            else:
                ok(f"{entry['id']}: matches {entry['repo']}@{entry.get('ref') or 'HEAD'} ({entry['version']})")

    print()
    if failures:
        print(f"RESULT: FAIL — {len(failures)} problem(s) across {checked} entries")
        return 1
    scope = "shape + local drift + network drift" if "--network" in sys.argv else "shape + local drift"
    print(f"RESULT: PASS — {checked} entries, {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
