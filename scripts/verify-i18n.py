#!/usr/bin/env python3
"""Every plugin in this repository owns its strings: this checks that they are complete.

Checks, per plugin directory (`<plugin-id>/plugin.json`):

1. `locales/en.json` and `locales/zh-CN.json` exist and hold the same keys.
2. Every `@key` in `plugin.json` is defined in both catalogs, and the translated text stays inside
   the length limits the host enforces.
3. Every `t("key")` / `_t("key")` call site in the plugin's Python modules is defined in both.
4. No user-facing Chinese string literal is left in code (docstrings and log lines are exempt:
   both are developer-facing and are never translated).
5. `registry.json` entries carry both `name`/`description` (English) and `name_zh`/`description_zh`.

Run from the repository root: `python3 scripts/verify-i18n.py`
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("en.json", "zh-CN.json")
CJK = re.compile(r"[\u4e00-\u9fff]")
#: Manifest fields that accept `@key`; `keywords` stays bilingual on purpose (search terms) and
#: `name` counts only at the top level — a parameter's `name` is an identifier, not display text.
KEY_FIELDS = ("description", "help", "title")
#: Literals that come from an upstream source rather than from us: they have to match the source
#: page's own labels to parse (zdic.net's 拼音 / 注音), so translating them would break the parse.
#: Keep this list tiny and reviewed; it applies to every plugin in this repository.
SOURCE_LABELS = {"拼音", "注音"}
LIMITS = {"name": 40, "description": 120, "title": 16}


def iter_manifest_strings(node, path=""):
    """Yield (dotted-path, field, value) for every manifest string that may hold an `@key`."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "keywords":
                continue
            here = f"{path}.{key}" if path else key
            if (key in KEY_FIELDS or (key == "name" and not path)) and isinstance(value, str):
                yield here, key, value
            else:
                yield from iter_manifest_strings(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_manifest_strings(value, f"{path}[{index}]")


def check_plugin(dir_path: Path, problems: list[str]) -> int:
    plugin_id = dir_path.name
    manifest = json.loads((dir_path / "plugin.json").read_text(encoding="utf-8"))

    catalogs: dict[str, dict[str, str]] = {}
    for lang in LANGS:
        path = dir_path / "locales" / lang
        if not path.is_file():
            problems.append(f"{plugin_id}: missing locales/{lang}")
            catalogs[lang] = {}
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
            problems.append(f"{plugin_id}: locales/{lang} must be a flat key → text object")
            data = {}
        catalogs[lang] = data

    if catalogs["en.json"].keys() != catalogs["zh-CN.json"].keys():
        only_en = sorted(set(catalogs["en.json"]) - set(catalogs["zh-CN.json"]))
        only_zh = sorted(set(catalogs["zh-CN.json"]) - set(catalogs["en.json"]))
        problems.append(f"{plugin_id}: locale keys differ — en-only {only_en} zh-only {only_zh}")

    # 2) @keys in the manifest, plus the host's length limits on the *translated* text
    for where, field, value in iter_manifest_strings(manifest):
        if value.startswith("@"):
            for lang in LANGS:
                if value[1:] not in catalogs[lang]:
                    problems.append(f"{plugin_id}: plugin.json {where} → {value} missing from {lang}")
        else:
            problems.append(f"{plugin_id}: plugin.json {where} is not a translatable @key: {value[:40]!r}")
        key = value[1:] if value.startswith("@") else ""
        limit = LIMITS.get(field.rsplit(".", 1)[-1])
        if key and limit:
            for lang, table in catalogs.items():
                text = table.get(key, "")
                if len(text) > limit:
                    problems.append(
                        f"{plugin_id}: {lang}: {field} resolves to {len(text)} chars (limit {limit})")

    trees: list[tuple[Path, ast.AST]] = []
    for path in sorted(dir_path.glob("*.py")):
        try:
            trees.append((path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))))
        except SyntaxError as exc:
            problems.append(f"{plugin_id}: {path.name}: does not parse — {exc}")

    # 3) t("key") call sites in every module
    used: set[str] = set()
    for path, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else "")
            if name not in ("t", "_t") or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                used.add(first.value)
            else:
                problems.append(
                    f"{plugin_id}: {path.name}:{node.lineno} t() called with a non-literal key")

    for key in sorted(used):
        for lang in LANGS:
            if key not in catalogs[lang]:
                problems.append(f'{plugin_id}: t("{key}") missing from {lang}')

    # 4) leftover Chinese user-facing literals
    for path, tree in trees:
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))

        def walk(node, in_log=False):
            if isinstance(node, ast.Call):
                func = node.func
                is_log = (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                          and func.value.id == "LOG")
                for child in ast.iter_child_nodes(node):
                    walk(child, in_log or is_log)
                return
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and not in_log and id(node) not in docstrings
                    and node.value not in SOURCE_LABELS and CJK.search(node.value)):
                problems.append(
                    f"{plugin_id}: {path.name}:{node.lineno} user-facing Chinese literal left"
                    f" — {node.value[:40]!r}")
            for child in ast.iter_child_nodes(node):
                walk(child, in_log)

        walk(tree)

    return len(catalogs["en.json"])


def check_registry(problems: list[str]) -> int:
    path = ROOT / "registry.json"
    if not path.is_file():
        problems.append("registry.json is missing")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        problems.append("registry.json has no `plugins` list")
        return 0
    for item in entries:
        plugin_id = item.get("id", "?")
        for field in ("name", "description"):
            if not str(item.get(field) or "").strip():
                problems.append(f"registry.json[{plugin_id}]: missing {field}")
            if not str(item.get(f"{field}_zh") or "").strip():
                problems.append(f"registry.json[{plugin_id}]: missing {field}_zh")
            elif CJK.search(str(item.get(field))):
                problems.append(
                    f"registry.json[{plugin_id}]: {field} must be English, not {item[field]!r}")
    return len(entries)


def main() -> int:
    problems: list[str] = []
    plugins = 0
    keys = 0
    for dir_path in sorted(ROOT.iterdir()):
        if not dir_path.is_dir() or not (dir_path / "plugin.json").is_file():
            continue
        plugins += 1
        keys += check_plugin(dir_path, problems)
    entries = check_registry(problems)

    print(f"checked {plugins} plugins, {keys} locale keys, {entries} registry entries"
          f" ({len(SOURCE_LABELS)} source labels allowed: {', '.join(sorted(SOURCE_LABELS))})")
    for problem in problems:
        print(f"  FAIL {problem}")
    print("RESULT:", "PASS" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
