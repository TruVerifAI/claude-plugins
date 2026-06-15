# TruVerifAI plugins for Claude Code

The official Claude Code marketplace for [TruVerifAI](https://truverif.ai).

## Install

Submit each slash command on its own — Claude Code parses one slash
command per submission. Pasting them all together produces a
malformed-URL error.

**1. Add the marketplace:**

```
/plugin marketplace add https://github.com/TruVerifAI/claude-plugins.git
```

**2. Install the plugin:**

```
/plugin install truverifai@truverifai
```

**3. Reload Claude Code's plugin set:**

```
/reload-plugins
```

**4. Configure your API key.** Run `/plugin`, click **Installed** →
**TruVerifAI**, paste your `tvai_…` key (generate one at
[truverif.ai/settings/api-keys](https://truverif.ai/settings/api-keys)),
click **Save configuration**, then run `/reload-plugins` again.

**5. Enable auto-update (recommended).** While you're in the `/plugin`
UI, click the **Marketplaces** tab, select **truverifai**, and toggle
**Enable auto-update** on. This is a one-time setting — once enabled,
future plugin updates (new skills, bug fixes, new tools) flow in
automatically on the next Claude Code session start. Without this,
you'd have to run the three-command manual update sequence below
every time a new version ships.

**6. Verify everything's wired up:** run `/truverifai-setup`.

## Manual update (only if you skipped Step 5)

If you didn't enable auto-update, pull the latest release with these
three commands (submit each on its own):

```
/plugin marketplace update truverifai
```

```
/plugin install truverifai@truverifai
```

```
/reload-plugins
```

## Uninstall

To remove the plugin (and optionally the marketplace registration), submit
each slash command on its own:

```
/plugin uninstall truverifai@truverifai
```

```
/reload-plugins
```

Optional — remove the marketplace registration too:

```
/plugin marketplace remove truverifai
```

## What's in here

| Plugin | Description |
|---|---|
| [`truverifai`](./plugins/truverifai) | Multi-model second-opinion deliberation for high-stakes coding decisions. Five skills — three primary (audit / deliberate / synthesize) that route your agent to TruVerifAI's MCP server, a follow-up (record-outcome) that fires after acting, and a gate-release skill (skip-gate-when-not-needed) — plus **proactive PreToolUse review gates** that prompt an audit before risky commits and a deliberation/synthesize before risky design changes (cross-domain risk classifier; releasable by a review or a logged `record_gate_skip`). Four frontier models reason independently and conflict-target each other's positions to produce decision-grade output; outcome reporting closes the loop with measurable per-call impact data on the dashboard. |

## Setup guide

For a walkthrough of how skills + adherence telemetry work after install:
[truverif.ai/settings/mcp](https://truverif.ai/settings/mcp) (sign in first).

For non-Claude-Code clients (Codex CLI, Goose, Cursor, Claude Desktop, VS
Code, Cline), the same page has manual MCP server setup snippets and
trigger-rule paste targets.

## Documentation

- [TruVerifAI homepage](https://truverif.ai)
- [Public MCP docs](https://truverif.ai/docs/mcp)
- [Skills guide](https://truverif.ai/docs/mcp)

## Support

- Email: [support@truverif.ai](mailto:support@truverif.ai)
- Issues: [github.com/TruVerifAI/claude-plugins/issues](https://github.com/TruVerifAI/claude-plugins/issues)

## License

MIT — see [LICENSE](./plugins/truverifai/LICENSE) inside each plugin.
