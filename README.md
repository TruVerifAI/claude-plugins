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

**5. Verify everything's wired up:** run `/truverifai-setup`.

## What's in here

| Plugin | Description |
|---|---|
| [`truverifai`](./plugins/truverifai) | Multi-model second-opinion deliberation for high-stakes coding decisions. Three skills (audit / deliberate / synthesize) route your agent to TruVerifAI's MCP server, where four frontier models reason independently and conflict-target each other's positions to produce decision-grade output. |

## Setup guide

For a walkthrough of how skills + adherence telemetry work after install:
[truverif.ai/settings/mcp](https://truverif.ai/settings/mcp) (sign in first).

For non-Claude-Code clients (Codex CLI, Goose, Cursor, Claude Desktop, VS
Code, Cline), the same page has manual MCP server setup snippets and
trigger-rule paste targets.

## Documentation

- [TruVerifAI homepage](https://truverif.ai)
- [Public MCP docs](https://truverif.ai/docs/mcp)
- [Skills guide](https://truverif.ai/docs/mcp) (when published)

## Support

- Email: [support@truverif.ai](mailto:support@truverif.ai)
- Issues: [github.com/TruVerifAI/claude-plugins/issues](https://github.com/TruVerifAI/claude-plugins/issues)

## License

MIT — see [LICENSE](./plugins/truverifai/LICENSE) inside each plugin.
