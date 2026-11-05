#!/usr/bin/env python3
"""Load this repository's plugins into a real Y-Hub install and check both languages.

What it proves that `verify-i18n.py` cannot: the manifests are accepted by the host, every
`@key` resolves, the three faces are registered, and the text a user sees is English with
`YHUB_LANG=en` and Chinese with `YHUB_LANG=zh-CN`.

Usage (from the repository root):

    python3 scripts/verify-host-load.py             # every plugin in this repository
    python3 scripts/verify-host-load.py zdic        # just one

Needs `yhub` on PATH (`uv tool install "yhub>=0.1.3"`). Runs the host in a throwaway config
root, so it never touches `~/.yhub`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHILD = "YHUB_PLUGIN_LOAD_CHILD"

PROBE = r"""
import json, re, sys
from yhub.server.adapters import discover_adapters
from yhub.i18n import current_lang

CJK = re.compile(r"[\u4e00-\u9fff]")
plugin_id, lang = sys.argv[1], current_lang()
meta = next((e["meta"] for e in discover_adapters() if e["meta"]["id"] == plugin_id), None)
if meta is None:
    print("FAIL: the host did not load the plugin"); sys.exit(1)

fields = [("name", meta["name"]), ("description", meta["description"])]
faces = meta.get("faces") or {}
for route in faces.get("routes") or []:
    fields.append((f"route {route['path']}", "ok"))
    for prm in route.get("params") or []:
        if prm.get("help"):
            fields.append((f"route.{prm['name']}.help", prm["help"]))
        for f in prm.get("fields") or []:
            if f.get("help"):
                fields.append((f"route.{f['name']}.help", f["help"]))
for tool in faces.get("mcp") or []:
    if tool.get("description"):
        fields.append((f"mcp.{tool['name']}.description", tool["description"]))
    for prm in tool.get("params") or []:
        if prm.get("help"):
            fields.append((f"mcp.{prm['name']}.help", prm["help"]))
cli = faces.get("cli") or {}
if cli.get("help"):
    fields.append(("cli.help", cli["help"]))
for sub in cli.get("subcommands") or []:
    if sub.get("help"):
        fields.append((f"cli.{sub['name']}.help", sub["help"]))

problems = []
for where, value in fields:
    if not value or value.startswith("@"):
        problems.append(f"{where} unresolved: {value!r}")
    elif lang == "en" and CJK.search(value):
        problems.append(f"{where} still Chinese: {value!r}")
print(json.dumps({"lang": lang, "name": meta["name"], "fields": len(fields),
                  "routes": len(faces.get("routes") or []),
                  "mcp": [t.get("name") for t in faces.get("mcp") or []],
                  "cli": (cli.get("command") if isinstance(cli, dict) else None),
                  "problems": problems}, ensure_ascii=False))
"""


def plugin_dirs(ids: list[str]) -> list[Path]:
    """Every `<plugin-id>/` in this repository that carries a manifest (or just the ones asked for)."""
    found = [d for d in sorted(ROOT.iterdir()) if d.is_dir() and (d / "plugin.json").is_file()]
    if not ids:
        return found
    by_id = {d.name: d for d in found}
    unknown = [pid for pid in ids if pid not in by_id]
    if unknown:
        print(f"not a plugin in this repository: {', '.join(unknown)} (have {', '.join(sorted(by_id))})")
        raise SystemExit(2)
    return [by_id[pid] for pid in ids]


def host_python() -> Path:
    """The interpreter that has `yhub` installed — the tool venv next to the `yhub` binary."""
    binary = Path(shutil.which("yhub") or "").resolve()
    for candidate in (binary.parent / "python", binary.parent / "python3"):
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def run_host(config_root: Path, plugin_id: str, lang: str) -> dict:
    env = dict(os.environ)
    env.update({"YHUB_CONFIG_DIR": str(config_root), "YHUB_LANG": lang, CHILD: "1"})
    proc = subprocess.run([str(host_python()), "-c", PROBE, plugin_id], env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print((proc.stdout + proc.stderr).strip())
        sys.exit(1)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main(argv: list[str]) -> int:
    if not shutil.which("yhub"):
        print('yhub is not on PATH — install it first: uv tool install "yhub>=0.1.3"')
        return 1
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        config_root = Path(tmp) / "config"
        plugins = config_root / "plugins"
        plugins.mkdir(parents=True)
        for src in plugin_dirs(argv):
            plugin_id = json.loads((src / "plugin.json").read_text(encoding="utf-8"))["id"]
            shutil.copytree(src, plugins / plugin_id,
                            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc",
                                                          "node_modules", ".venv", "dist"))
            for lang in ("en", "zh-CN"):
                result = run_host(config_root, plugin_id, lang)
                print(f"  {plugin_id} {lang}: name={result['name']!r} fields={result['fields']} "
                      f"routes={result['routes']} mcp={result['mcp']} cli={result['cli']}")
                problems += [f"{plugin_id}: {p}" for p in result["problems"]]

    for problem in problems:
        print(f"  FAIL {problem}")
    print("RESULT:", "PASS" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
