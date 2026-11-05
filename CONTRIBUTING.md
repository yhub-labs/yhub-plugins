# Contributing a plugin

This repository is Y-Hub's **default plugin index**: `registry.json` is what every host fetches to make
`yhub plugin search` and `yhub plugin install <id>` work out of the box. Adding a plugin means adding
one entry to that file — the code stays in **your** repository, on **your** release cycle.

Two exceptions worth knowing:

* you want the code hosted here (we review, tag and release it) — see [Option B](#option-b-host-the-code-here);
* your plugin is a monorepo that already ships several plugins — `registry.json` supports `subdir`.

## Option A — keep your own repository (the normal path)

1. **Publish the plugin repository.** Public on GitHub, `plugin.json` at the repository root, and the
   host's rules apply: schema 2, `id` lowercase-with-hyphens and identical to the directory name,
   `version` as `x.y.z`, explicit `trust`, `name` ≤ 30 chars, `description` ≤ 120 chars. The full contract
   is [docs/plugins.md](https://github.com/yhub-labs/yhub/blob/main/docs/plugins.md); the quickest sanity
   check is that the host loads it — copy the directory into `<config>/plugins/<id>/` and start `yhub`.
2. **Set `min_yhub` honestly.** It is the host version whose API you actually use (`presentation.panel`
   needs 0.1.2, plugin-owned translations need 0.1.2, `@key` in the manifest needs 0.1.1 …). A plugin
   that declares too low a floor is installed on a host that cannot run it.
3. **Tag the version you want shipped** (`v1.0.0` is the convention). The index pins a tag, so a later
   push to `main` cannot silently change what people install.
4. **Open a PR here that adds exactly one entry** to `registry.json`, keeping the file's ordering and
   formatting:

   ```json
   {
     "id": "your-plugin",
     "name": "Your plugin",
     "name_zh": "中文名",
     "description": "One English sentence — what it does, not how it is built",
     "description_zh": "一句中文，与英文同义",
     "repo": "you/your-plugin-repo",
     "version": "1.0.0",
     "min_yhub": "0.1.7",
     "ref": "v1.0.0"
   }
   ```

   `name_zh` / `description_zh` are required: the index is fetched before any plugin (or its locale
   files) exists, so the Chinese UI can only read these fields. `keywords` are not copied here — search
   happens in the plugin's own manifest.

5. **Run the checks before pushing** (they run in CI too):

   ```bash
   python3 scripts/verify-registry.py            # shape: ids, one source, version, pinned ref
   python3 scripts/verify-registry.py --network  # your plugin.json at the pinned ref must agree
   ```

   `--network` is the real gate for an external entry: it fetches
   `raw.githubusercontent.com/<repo>/<ref>/plugin.json` and fails when `version`, `min_yhub` or `id`
   disagree with the entry. If it passes locally, CI will pass.

### What a maintainer reviews

* **One entry, nothing else** — a PR that touches `zdic/` or `memos/` is a different conversation.
* The id is stable, descriptive and not already taken (`yhub plugin search <id>` shows the current set).
* The entry points at a real, public repository; the tag exists and its `plugin.json` matches the entry.
* The plugin speaks the host's public API only: `yhub.plugin_api` (`ToolError`, `translator`), standard
  library and what the host already ships. A plugin that needs a patch to the host to work is not
  ready for the index.
* No secrets, no auto-installing dependencies, no network call at import time, honest failure
  (`ToolError` + a hint) instead of a fake empty result.
* The description says what a user gets, in one line of plain language.

Maintainers may decline an entry that cannot be installed reproducibly, shadows a core tool, or is
already abandoned. An entry is removed again if its repository disappears, its tag no longer resolves,
or it stops loading on the `min_yhub` it declares.

### Testing the exact install path

Before opening the PR, install the way the index will:

```bash
yhub plugin install you/your-plugin-repo@v1.0.0       # pinned tag, no registry involved
yhub plugin install ~/Projects/your-plugin --id your-plugin   # local checkout, same files
```

## Option B — host the code here

If you would rather not run a release cycle, the plugin can live in this repository: add
`<id>/` (`plugin.json`, `plugin.py`, `locales/`, optional `panel/index.html`, a `README.md`) and an entry
with `"repo": "yhub-labs/yhub-plugins"`, `"subdir": "<id>"`, `"ref": "<id>-v<version>"`. One repository
carries several release lines, so tags are prefixed; `scripts/verify-registry.py` enforces the
`version` / `min_yhub` / `ref` triple against the in-repo manifest, and CI additionally loads every
plugin in both languages (`scripts/verify-host-load.py`).

Please open an issue first: the code is then maintained here, and that is a bigger commitment than one
entry in a JSON file.
