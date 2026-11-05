# Zdic, a Y-Hub plugin

Look up Chinese characters and words — pronunciation, radicals, stroke count and definition — from [zdic.net](https://www.zdic.net), with the same declaration exposed on three faces at once: an HTTP route (`GET /api/zdic`), an MCP tool (`zdic_lookup`) and a CLI command (`yhub zdic`).

```bash
yhub plugin install zdic                                   # by registry id (the default index)
yhub plugin install ~/Projects/yhub-plugins/zdic --id zdic  # from a local checkout
yhub zdic 你                                       # CLI
curl 'http://127.0.0.1:8790/api/zdic?q=你'         # same data, HTTP
```

Requires Y-Hub ≥ 0.1.2 (plugin-owned translations, hosted panels).

## What it does

* scrapes the public Zdic entry and parses out pinyin, zhuyin, radicals, stroke counts, definitions and the English gloss where the entry has one;
* returns the same body shape on all three faces, so `yhub zdic --json` and `GET /api/zdic` agree byte for byte;
* reports a missing word as `ToolError` with a hint instead of an empty result — `汉典未收录「X」` / `Zdic has no entry for “X”`;
* never asks a model: every field comes from the page.

## Layout

```text
plugin.json        declaration: id, name, faces (routes / mcp / cli), localizable @keys
plugin.py          three-face glue (route, MCP handler, CLI main) + config hooks
zdic_impl.py       fetch and parse (vendored: a plugin cannot import host internals)
locales/en.json    every user-facing string, English
locales/zh-CN.json same keys, Chinese
panel/index.html    the tool page: one self-contained file, served by the host
```

Verification lives at the repository root (`scripts/`), because it checks every plugin here. Run this
plugin's own checks from there:

```bash
python3 scripts/verify-i18n.py             # parity, @keys, t("…") call sites, leftover Chinese
python3 scripts/verify-host-load.py zdic  # load this plugin into a real host, in both languages
```

## Translations

The plugin owns its strings. `plugin.json` declares `"name": "@name"` and `"help": "@param.q"`; `plugin.py` translates at runtime:

```python
from yhub.plugin_api import translator
t = translator("zdic")
raise ToolError(str(exc), hint=t("err.hint.network"))
```

The host registers `locales/*.json` as `plugins.zdic.*` and resolves every `@key` before validating the manifest, so length limits apply to the translated text. A key missing from a catalog is a startup error naming it — it never shows up as `@key` on screen. `keywords` stay bilingual on purpose (launcher search terms), and log lines are not translated.

## Panel

`panel/index.html` is the tool page: one self-contained HTML file with inline CSS and JS, no build
step. The host serves it at `/api/plugins/zdic/panel` (declared as `"presentation": {"panel":
"panel/index.html"}`) and the workbench shows it in an iframe, so the only contract is the HTTP API —
nothing here imports the host's React tree.

`?q=你` (and `&traditional=1`) looks a word up on load, which makes the panel URL shareable. The
language follows `/api/settings:ui_language`. Requires Y-Hub ≥ 0.1.2, the release that serves panels.
