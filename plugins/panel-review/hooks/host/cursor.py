"""Cursor host adapters — TWO surfaces with different event delivery (plan §7.2).

CursorHost (IDE): the marketplace plugin fires `preToolUse` for all tool types
(matcher `Write`) and `beforeShellExecution` for shell. The write gate binding
is ASSUMED to deny per the owner decision (plan §0) — the `write_gate_ASSUMED`
capability drives COPY/doctor output only, never registration.

CursorCliHost (cursor-agent): the 2026-07 observation was commit-gate-only
(shell events only). That is obsolete — the 2026-08-01 C4 cert run confirmed
the CLI fires preToolUse for Write too, so both surfaces run the full dual
gate from the same user-level `~/.cursor/hooks.json`. The forward-compatible
registration (§2.5 rule 1) is what made this a zero-change upgrade: the day
Cursor delivered the event, the gate just worked.

Wire contract (cursor.com/docs/agent/hooks):
- input: snake_case (tool_name/tool_input/cwd), conversation-scoped ids; write
  tool type is `Write`, shell is `Shell` with camelish input shapes -> mapped
  by shape.
- deny: stdout {"permission": "deny", "agent_message": ..., "user_message":
  ...} — agent_message reaches the MODEL (the routing text), user_message the
  human. exit 0 = parsed; other non-zero = fail open. `ask` is accepted by the
  schema but NOT enforced -> emit_ask degrades to allow-with-warning (the base
  contract: an unsupported ask must never hard-trap).
"""

import json
import os
import re
import sys

from host.base import Host, brand


class CursorHost(Host):
    name = "cursor"

    capabilities = dict(Host.capabilities, **{
        "install": "user_hooks_config",    # ~/.cursor/hooks.json via tvai init (IDE + CLI)
        # CONFIRMED LIVE 2026-08-01 (cursor 3.14.7, Windows): preToolUse
        # delivered a Write with claude-shaped tool_input; the write gate
        # fired, an audit PASS released it, and the retry proceeded.
        "write_gate": "confirmed_live_2026_08",
        "supports_ask": True,              # "permission": "ask" is in the documented contract
        "supports_advisory_context": False,
        "separate_user_message": True,
        "stderr_reaches_model": "unknown",
    })

    manifest_paths = (
        "/".join((".cursor-plugin", "plugin.json")),
    ) + Host.manifest_paths

    # -- input -------------------------------------------------------------

    @staticmethod
    def _fs_path(p):
        # Cursor's workspace_roots are URI-style on Windows ("/C:/temp/x") —
        # invalid as a filesystem path (live capture 2026-08-01, cursor
        # 3.14.7). Strip the leading slash ONLY for the drive-letter pattern
        # on Windows; POSIX roots ("/home/x") have no colon and pass through.
        if os.name == "nt" and isinstance(p, str) and \
                re.match(r"^/[A-Za-z]:[/\\]", p):
            return p[1:]
        return p

    def normalize_input(self, raw):
        out = dict(raw or {})
        # beforeShellExecution delivers the command TOP-LEVEL — no tool_name,
        # no tool_input: {"command": ..., "cwd": "", ...} (live capture
        # 2026-08-01). Synthesize the claude shape the gates key on. Guarded
        # on tool_name being absent/empty so a named tool is never overridden;
        # merge into any existing tool_input rather than clobbering it.
        cmd = out.get("command")
        if not out.get("tool_name") and isinstance(cmd, str) and cmd:
            ti0 = dict(out.get("tool_input") or {})
            # Precedence: an existing tool_input["command"] wins even when
            # falsy ("" / None) — never override what the host sent.
            ti0.setdefault("command", cmd)
            out["tool_name"] = "Bash"
            out["tool_input"] = ti0
            if os.environ.get("TVAI_DEBUG"):
                sys.stderr.write(
                    "TruVerifAI debug: synthesized Bash from top-level "
                    "command (event=%s)\n" % out.get("hook_event_name"))
        # cwd insurance (docs sweep 2026-07-31): USER-level hooks execute with
        # process cwd = ~/.cursor, so the gates depend entirely on the payload
        # cwd. Live capture: payload cwd is an EMPTY STRING and
        # workspace_roots is the only usable location — map the variants; a
        # missing cwd would make the commit gate diff ~/.cursor (silent no-op).
        if not out.get("cwd"):
            wr = out.get("workspace_roots")
            cand = (wr[0] if isinstance(wr, list) and wr else None) or \
                out.get("workspace_root") or out.get("project_dir") or \
                out.get("workspace_dir")
            # Strings only (audit F-005): a malformed entry must not become a
            # cwd — leave it unset and let downstream fall back safely.
            if cand and isinstance(cand, str):
                out["cwd"] = self._fs_path(cand)
        tool = str(out.get("tool_name") or "")
        ti = out.get("tool_input") or {}
        if tool in ("Shell", "shell"):
            out["tool_name"] = "Bash"
            if "command" not in ti:
                cmd = ti.get("cmd") or ti.get("commandLine") or ti.get("input")
                if isinstance(cmd, str):
                    ti = dict(ti)
                    ti["command"] = cmd
            out["tool_input"] = ti
            return out
        if tool in ("Write", "write", "Edit", "edit"):
            # Cursor's Write input shape isn't exhaustively documented; if it
            # already looks claude-shaped, keep it, else map by shape.
            if "file_path" in ti and ("content" in ti or "new_string" in ti):
                return out
            mapped_tool, mapped_ti = self.map_write_input(ti)
            if mapped_tool:
                out["tool_name"] = mapped_tool
                out["tool_input"] = mapped_ti
        return out

    # -- output ------------------------------------------------------------

    def emit_deny(self, reason, system_message=None):
        out = {"permission": "deny", "agent_message": reason}
        if system_message:
            out["user_message"] = system_message
        print(json.dumps(out))
        sys.exit(0)

    def emit_ask(self, reason, system_message=None):
        # REAL ask (docs sweep 2026-07-31): "permission": "ask" is part of
        # Cursor's documented output contract for preToolUse /
        # beforeShellExecution — the human-confirmation channel works natively
        # here. (The old TVAI_ASK_DEGRADED allow-with-warning predated the
        # docs; degradation now applies only on hosts without ask.)
        out = {"permission": "ask", "agent_message": reason}
        if system_message:
            out["user_message"] = system_message
        print(json.dumps(out))
        sys.exit(0)

    def emit_allow_advisory(self, additional_context):
        try:
            sys.stderr.write(brand(additional_context) + "\n")
        except Exception:
            pass
        sys.exit(0)

    def emit_post_advisory(self, message, event_name="PostToolUse"):
        # Cursor postToolUse/postToolUseFailure output contract
        # (cursor.com/docs/agent/hooks, verified 2026-08-01): snake_case
        # additional_context injects into the conversation. afterShellExecution
        # is observational-only — the backstop rides postToolUse instead.
        try:
            print(json.dumps({"additional_context": message}))
            sys.stdout.flush()
        except Exception:
            pass


class CursorCliHost(CursorHost):
    name = "cursor_cli"

    capabilities = dict(CursorHost.capabilities, **{
        "install": "hooks_config_file",            # .cursor/hooks.json via tvai init
        # CONFIRMED LIVE 2026-08-01 (C4 cert run, CLI on Windows): the 2026-07
        # "not delivered" observation is obsolete — cursor-agent now fires
        # preToolUse for Write; the write gate denied G2 and released on audit.
        "write_gate": "confirmed_live_2026_08",
    })
