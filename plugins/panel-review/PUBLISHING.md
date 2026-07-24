# Publishing the TruVerifAI plugin

This file documents how to publish this plugin to the
`github.com/TruVerifAI/claude-plugins` marketplace repository.

The plugin is developed in this monorepo under `plugin/`. The marketplace
repository has a slightly different layout (an outer `plugins/<name>/`
wrapper + a `.claude-plugin/marketplace.json` at the root). The
publishing flow copies our `plugin/` into the right slot in the
marketplace repo.

---

## The two-repo flow

There are **two separate git repos** (sibling folders under
`C:\Code\AI-aggregator\`), each with its own GitHub remote. The plugin's
**source of truth** is `plugin/` in the app repo; the marketplace repo holds a
**distribution copy**.

| | App repo (dev source) | Marketplace repo (published) |
|---|---|---|
| Local path | `…/ai-aggregator` | `…/claude-plugins` (sibling, `../claude-plugins`) |
| GitHub remote | `vivekpolavarapu/ai-aggregator` | `TruVerifAI/claude-plugins` |
| Plugin path | `plugin/` (authority) | `plugins/panel-review/` (copy) |
| Consumed by | the TruVerifAI app | Claude Code users installing the plugin |

```
  ① edit dev source          ② sync (local file copy)        ③ push
  ai-aggregator/plugin/ ──────────────────────────► claude-plugins/plugins/panel-review/
       │                   [cp local→local, LF-fix hooks,           │
       │ ③ push             drop PUBLISHING.md, keep CHANGELOG.md,   │ push
       ▼                    bump version]                           ▼
  github:                                                    github:
  vivekpolavarapu/ai-aggregator                              TruVerifAI/claude-plugins
       │                                                            │
  (the app deploys from here)                  users: /plugin install panel-review@truverifai
                                                      (pull from here)
```

**Key properties:**

- **Two independent pushes.** Pushing the app repo does NOT update the
  marketplace, and vice-versa. "Republish" is always a deliberate, separate step.
- **The sync is a local file copy** from `ai-aggregator/plugin/` into
  `claude-plugins/plugins/panel-review/` — it does NOT go through GitHub.
- **One-directional + manual.** `plugin/` is always the authority; re-sync the
  marketplace copy from it on every release. The two can drift if you edit one
  side and forget the other (CLAUDE.md Rule 9).
- **Exclude / preserve on copy:** drop dev-only `PUBLISHING.md`; keep
  marketplace-only `CHANGELOG.md`; force **LF** on `hooks/` + `hooks.json`
  (the marketplace repo has no `.gitattributes` to normalize them).
- **Always bump the version** in BOTH `marketplace.json` and the bundled
  `plugin.json` — Claude Code caches installs by version, so a same-version
  content change won't reach users.

---

## Marketplace repo layout

```
TruVerifAI/claude-plugins/                      <- the marketplace repo
├── .claude-plugin/
│   └── marketplace.json                         <- marketplace metadata (see below)
├── plugins/
│   └── panel-review/                            <- our plugin lives here
│       ├── .claude-plugin/
│       │   └── plugin.json                     <- (copied from this repo)
│       ├── .mcp.json
│       ├── skills/                              <- the five skill dirs
│       ├── commands/
│       ├── hooks/
│       ├── hooks.json
│       ├── README.md
│       └── LICENSE
└── README.md                                    <- marketplace README
```

---

## `marketplace.json` contents

Create `.claude-plugin/marketplace.json` at the root of the marketplace
repo with this content (adjust the version on each release):

```json
{
  "name": "truverifai",
  "owner": {
    "name": "TruVerifAI",
    "email": "support@truverif.ai",
    "url": "https://truverif.ai"
  },
  "metadata": {
    "description": "Multi-model second-opinion deliberation for high-stakes coding and finance decisions. Eight skills (audit / deliberate / synthesize, per profile, plus record-outcome and skip-gate) route to the TruVerifAI MCP server, where four frontier models reason independently and conflict-target each other's positions to produce decision-grade output.",
    "version": "0.1.0"
  },
  "plugins": [
    {
      "name": "panel-review",
      "source": "./plugins/panel-review",
      "description": "Multi-model second-opinion deliberation for high-stakes coding decisions"
    }
  ]
}
```

---

## Publishing steps

### First-time setup

1. Create the GitHub repo at `https://github.com/TruVerifAI/claude-plugins`. Make it public.
2. Add `vivekpolavarapu` as a collaborator (already done per Plan §7 Q3 operational notes).
3. Clone it locally to a sibling directory, e.g.:
   ```bash
   git clone git@github.com:TruVerifAI/claude-plugins.git ../claude-plugins
   ```
4. Create the marketplace skeleton:
   ```bash
   cd ../claude-plugins
   mkdir -p .claude-plugin plugins
   # Create .claude-plugin/marketplace.json from the template above
   ```

### Each release

1. **Bump the version** in `plugin/.claude-plugin/plugin.json` in this repo (the AI-aggregator monorepo). Per Anthropic's plugin docs: if `version` is set, you MUST bump it on every release — pushing new commits alone is not enough for users to pick up changes.
2. **Test locally** in your dev workspace:
   ```bash
   # From the AI-aggregator repo root:
   cd plugin
   # Try the cross-platform install script to verify it works:
   ./install-cross-platform.sh --tool=cursor   # or similar
   ```
3. **Sync** to the marketplace repo:
   ```bash
   # From the AI-aggregator repo root:
   rm -rf ../claude-plugins/plugins/panel-review
   cp -r plugin ../claude-plugins/plugins/panel-review

   # Verify the marketplace.json version matches plugin.json's version
   ```
4. **Validate** (if `claude` CLI is installed):
   ```bash
   cd ../claude-plugins
   claude plugin validate
   ```
5. **Commit + push** in the marketplace repo:
   ```bash
   cd ../claude-plugins
   git add .
   git commit -m "feat: v0.1.0 release"
   git push origin main
   ```
6. **Tag the release** (optional but recommended for changelog clarity):
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

### After first release

Submit to Anthropic's `claude-community` marketplace via:

- claude.ai/settings/plugins/submit
- platform.claude.com/plugins/submit

Approval is async; the marketplace can ship and be installable from
the GitHub URL before community-marketplace approval lands.

---

## Verifying the install works

After publishing, in a fresh Claude Code project:

```bash
/plugin marketplace add TruVerifAI/claude-plugins
/plugin install panel-review@truverifai
```

You should be prompted for `api_token` (the gate/borderline options have
defaults and don't require input at install). After install, run
`/panel-review:setup` to verify connectivity.

---

## Branding / account notes

- The GitHub account is `TruVerifAI` (user account, not org). Per Plan §7
  Q3, we'll convert to an org later when there's a business reason
  (incorporation, team growth). GitHub preserves URLs through that
  transition.
- A few small commits from the `TruVerifAI` account over several days
  before the actual plugin launch makes the account look like an
  established maintainer instead of a brand-new account, which raises
  install-trust signals.

---

## Updating after publish

To ship an update:

1. Make the changes in this monorepo (`plugin/...`).
2. Bump `version` in `plugin/.claude-plugin/plugin.json`.
3. Bump the version in the marketplace's `marketplace.json` to match.
4. Follow the "Each release" steps above.

Users will pick up the update via:

- Auto-update at next Claude Code startup (default behavior for marketplaces).
- Manual: `/plugin update panel-review`.

---

## Rollback

If a release ships with a bug:

1. Revert the marketplace repo to the last good commit:
   ```bash
   cd ../claude-plugins
   git revert HEAD
   git push origin main
   ```
2. Users on the bad version will auto-update to the reverted-to version
   at next Claude Code startup.

The `commands/`, `hooks/`, and `skills/` directories are file-based, so
a revert is sufficient — no DB state on the plugin side.

The MCP server's state (telemetry rows, etc.) is independent of plugin
versions, so rollbacks don't affect data.
