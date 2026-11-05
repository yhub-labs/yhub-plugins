# Memos, a Y-Hub plugin

Read and write [Memos](https://github.com/usememos/memos) notes without leaving Y-Hub, with the same declaration exposed on three faces at once: an HTTP route (`GET /api/memos`, `POST /api/memos`), MCP tools (`memos_list` / `memos_create`) and a CLI command (`yhub memos`).

```bash
yhub plugin install memos                                    # by registry id (the default index)
yhub plugin install ~/Projects/yhub-plugins/memos --id memos  # from a local checkout
yhub memos list today                                       # CLI
curl 'http://127.0.0.1:8790/api/memos?day=today&limit=20'    # same data, HTTP
yhub memos new 今天读完了第三章                                # write
```

Requires Y-Hub ≥ 0.1.3.

## What it does

* lists your memos by day (`today` / `yesterday` / `all` / `YYYY-MM-DD`), newest first, with tags;
* posts a new memo, and reports upstream failures as `ToolError` with a hint instead of an empty list;
* keeps the instance URL and access token in the host config root's `.env` (`YHUB_MEMOS_INSTANCE` / `YHUB_MEMOS_TOKEN`) — **values are never printed**, not by the CLI, not by `/api/memos/config`, not in logs;
* never asks a model: it is a thin client for your own instance.

## Configuration

Two values: the instance URL and an access token. Either set them in Y-Hub's settings page (`POST /api/memos/config` writes them) or run `yhub memos auth`. `GET /api/memos/config` reports `configured`, `instance` and `config_path` — never the token.

## Layout

```text
plugin.json          declaration: id, name, faces (routes / mcp / cli), localizable @keys
plugin.py            three-face glue (routes, MCP handlers, CLI main) + config hooks
memos_impl.py        HTTP client for the Memos API (vendored: a plugin cannot import host internals)
locales/en.json      every user-facing string, English
locales/zh-CN.json   same keys, Chinese
panel/index.html     the tool page: one self-contained file, served by the host
```

Verification lives at the repository root (`scripts/`), because it checks every plugin here:

```bash
python3 scripts/verify-i18n.py              # parity, @keys, t("…") call sites, leftover Chinese
python3 scripts/verify-host-load.py memos   # load this plugin into a real host, in both languages
```

## Translations

The plugin owns its strings. `plugin.json` declares `"name": "@name"` and `"help": "@param.day"`; `plugin.py` translates at runtime:

```python
from yhub.plugin_api import translator
t = translator("memos")
raise ToolError(t("err.not_configured"), hint=t("err.not_configured.hint"))
```

The host registers `locales/*.json` as `plugins.memos.*` and resolves every `@key` before validating the manifest, so length limits apply to translated text. A missing key is a startup error naming it — it never shows up as `@key` on screen.

## Panel

`panel/index.html` is the tool page: one self-contained HTML file with inline CSS and JS, no build step. The host serves it at `/api/plugins/memos/panel` (declared as `"presentation": {"panel": "panel/index.html"}`) and the workbench shows it in an iframe, so the only contract is the HTTP API — nothing imports the host's React tree.

Today / Yesterday / All switch the list; the box posts a new memo (`⌘↵`); `?day=yesterday` deep-links to a range. When the plugin is not configured the panel says so and points at the settings page rather than showing an empty list. The language follows `/api/settings:ui_language`.
