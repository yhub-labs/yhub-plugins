# Y-Hub Plugins

Third-party plugins for [Y-Hub](https://github.com/yhub-labs/yhub): the tools that ship on their own
release cycle instead of inside the host.

| Plugin | What it does |
| --- | --- |
| [`zdic`](zdic/) | Chinese characters and words: pinyin, radicals, stroke counts, definitions |
| [`memos`](memos/) | Your [Memos](https://github.com/usememos/memos) notes by day, plus a compose box |

Each directory is one plugin (`plugin.json` + `plugin.py` + `locales/` + optional `panel/`), and
`registry.json` is the static index consumed by `yhub plugin search/install`.

This registry is Y-Hub's **default** plugin index (`DEFAULT_REGISTRY_URL` in the host's
`settings.py`), so no configuration is needed:

```bash
yhub plugin search zdic            # lists what this index offers
yhub plugin install zdic           # by id: resolves through the index
yhub plugin install zdic --force   # reinstall/upgrade over an existing copy
```

An install by id is reproducible: every entry pins a `ref` (a tag), so `yhub plugin install zdic`
fetches exactly the version the index names, not whatever `main` is today. Plugins in this
repository are tagged `<plugin-id>-v<version>` (`zdic-v0.1.3`, `memos-v0.1.3`), because one
repository carries two independent release lines.

Installing straight from the checkout also works — the installer takes a subdirectory:

```bash
yhub plugin install yhub-labs/yhub-plugins#zdic              # from GitHub, by subdirectory
yhub plugin install ~/Projects/yhub-plugins/zdic --id zdic   # from a local checkout
```

An install **by id** from an entry that carries `subdir` needs a host that merges the index entry's
`subdir` into the GitHub install path (Y-Hub ≥ 0.1.8; before that it unpacked the repository root and
refused the wrong plugin). On an older host, name the subdirectory explicitly as above.

## Adding a third-party plugin

Plugins from other people are **not** copied into this repository: they keep their own repository and
release cycle, and the PR here adds **one entry** to `registry.json` (`repo` + pinned `ref`, plus
`subdir` only when their repository is itself a monorepo). The index is what `yhub plugin install <id>`
resolves; the code never leaves the author's repo.

The entry must carry `name_zh`/`description_zh` (the index is fetched before any plugin exists, so the
Chinese UI can only read them), a real tag, and a `min_yhub` that matches what the plugin actually needs.
`python3 scripts/verify-registry.py --network` is the gate: it fetches the plugin's `plugin.json` at the
pinned tag and fails when `version` / `min_yhub` / `id` disagree.

Step-by-step, review criteria and the alternative (hosting the code here) live in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Releasing a plugin

Bump the plugin's `plugin.json`, update its `registry.json` entry (`version`, `min_yhub`, `ref` — all
three must match), tag `<plugin-id>-v<version>`, then push the tag. The check below is what enforces
the first two locally:

```bash
python3 scripts/verify-registry.py            # shape + drift against zdic/ and memos/
```

Plugins run as arbitrary Python code inside the host process. Install only plugins you trust. See
[docs/plugins.md](https://github.com/yhub-labs/yhub/blob/main/docs/plugins.md).

## Layout

```text
<plugin-id>/
  plugin.json
  plugin.py
  <plugin-id>_impl.py   # vendored logic: a plugin cannot import host internals
  locales/              # en.json + zh-CN.json — the plugin's own strings
  panel/index.html      # optional tool page, served by the host at /api/plugins/<id>/panel
scripts/                # verification (see below)
registry.json
```

Plugin releases are tagged as `<plugin-id>-v<version>`; `registry.json` is the source of truth for
the catalog.

## Check before pushing

```bash
python3 scripts/verify-i18n.py        # locale parity, @keys, t("…") call sites, leftover Chinese, registry
python3 scripts/verify-registry.py    # entry shape + drift against each plugin.json
python3 scripts/verify-registry.py --network   # external entries: their plugin.json at the pinned tag
python3 scripts/verify-host-load.py   # load every plugin into a real host, in both languages
```

`verify-host-load.py` needs `yhub` on PATH (`uv tool install "yhub>=0.1.3"`) and runs in a throwaway
config root, so it never touches `~/.yhub`. CI runs all three.

## Panels

Both plugins ship a **single self-contained HTML file** under `panel/index.html`, declared as
`"presentation": {"panel": "panel/index.html"}`. The host serves it at `GET /api/plugins/<id>/panel`
and the workbench shows it in an iframe, so the only contract is the HTTP API — nothing imports the
host's React tree. Details: [docs/panels.md](docs/panels.md).

## Translating a plugin

Plugins own their strings; the host catalog only knows the core's. Each plugin ships
`locales/en.json` and `locales/zh-CN.json` (flat `{"key": "text"}`, `{param}` placeholders filled by
the host), declares `"name": "@name"` and friends in `plugin.json`, and calls
`translator("<plugin-id>")` from `plugin.py`:

```python
from yhub.plugin_api import translator
t = translator("memos")
raise ToolError(t("err.hint.network"))
```

`keywords` stay bilingual on purpose (search terms, not display text), `name`/`description` in the
manifest are `@keys`, and log lines stay untranslated because they are developer-facing.
`registry.json` entries carry English `name`/`description` plus `name_zh`/`description_zh`, since
registry metadata is fetched before anything is installed.

Host-side mechanics: [docs/plugins.md §9](https://github.com/yhub-labs/yhub/blob/main/docs/plugins.md).
