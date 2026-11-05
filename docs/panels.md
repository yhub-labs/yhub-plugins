# Panels — the frontend half of a plugin

A plugin can ship its own tool page. The declaration is one key in `plugin.json`:

```jsonc
"presentation": { "panel": "panel/index.html" }
```

The host serves that file at `GET /api/plugins/<id>/panel` (`text/html`, `Cache-Control: no-store`, a
permissive-but-sane CSP) and `/api/tools` then carries `"panel": "/api/plugins/<id>/panel"` for the
tool. The workbench renders that URL in an `<iframe class="tool-panel-frame">`; a tool with neither a
core panel nor a declared one still shows the "no panel yet" placeholder.

Why an iframe instead of importing the plugin's React component: the frontend is compiled into the
host bundle at build time, so a runtime `import()` of third-party code would tie every plugin to the
host's React tree, component paths and i18n provider — and a plugin written in anything else could
not ship a screen at all. An iframe has exactly one contract, the HTTP API, which the plugin already
speaks. The panel can still reach `/api/*` (same origin) and reads the UI language from
`/api/settings:ui_language`.

Rules the loader enforces at startup (a bad declaration is red, never a dead page): the value is a
string, a relative path inside the plugin directory (no `..`, no absolute), and the file exists.

Serving is gated on the **loaded** plugin set, not on the directory: a plugin marked `disabled` leaves
its files in place, and its panel must disappear with its tool. Every "no screen here" case — unknown
id, installed but not loaded, no declaration, file deleted after install — answers **404**.

## The two panels here

| Plugin | Panel | Routes it calls |
| --- | --- | --- |
| `zdic` | `zdic/panel/index.html` | `GET /api/zdic` |
| `memos` | `memos/panel/index.html` | `GET`/`POST /api/memos/config`, `GET`/`POST /api/memos` |

Both are single self-contained HTML files — inline CSS and JS, no build step, no host imports — so the
only thing they need from the host is the panel URL and the HTTP API. `zdic` uses `?q=你` for
shareable deep links; `memos` uses `?day=yesterday` and shows a "configure me" state instead of an
empty list when no instance is set.
