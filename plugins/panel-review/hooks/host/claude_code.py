"""Claude Code host adapter — the reference platform.

The base class already IS the Claude Code wire behavior; this adapter only adds
the native config mechanism (plugin `userConfig` options injected as
`CLAUDE_PLUGIN_OPTION_*` env vars) so the extraction stays behavior-identical
to plugin v0.17.0 (phase-0 bar).
"""

import os

from host.base import Host


class ClaudeCodeHost(Host):
    name = "claude_code"

    # The marketplace plugin updates via the /plugin UI (no CLI surface for
    # a running session) — the agent surfaces this to the human.
    update_instruction = ("To update, ask the user to update panel-review in "
                          "/plugin, then run /reload-plugins.")

    capabilities = dict(Host.capabilities, **{
        # `additionalContext` + `ask` are documented; whole surface identical to base.
        "install": "marketplace_plugin",
    })

    def native_option(self, name):
        # userConfig options arrive as CLAUDE_PLUGIN_OPTION_<UPPER_SNAKE>.
        return os.environ.get("CLAUDE_PLUGIN_OPTION_" + name.upper())
