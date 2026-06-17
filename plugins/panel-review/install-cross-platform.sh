#!/usr/bin/env bash
# TruVerifAI plugin — cross-platform install for non-Claude-Code agents.
#
# Claude Code users should NOT run this script — install via the plugin
# system instead:
#   /plugin marketplace add truverifai/claude-plugins
#   /plugin install panel-review@truverifai
#
# This script is for Codex CLI, Gemini CLI, and Cursor users who want
# to install the TruVerifAI skills + connect to the MCP server manually.
#
# Usage:
#   ./install-cross-platform.sh             # auto-detect tool
#   ./install-cross-platform.sh --tool codex   # explicit tool
#   ./install-cross-platform.sh --tool gemini
#   ./install-cross-platform.sh --tool cursor
#   ./install-cross-platform.sh --tool all      # copy to every detected tool
#
# What it does:
#   1. Detects which AI coding tool you have configured.
#   2. Copies the three skill directories to that tool's skills folder.
#   3. Prints instructions for adding the TruVerifAI MCP server to the
#      tool's MCP config (varies per tool — we can't write the config
#      for you because it usually requires your API key inline).
#
# What it does NOT do:
#   - Install Claude Code's plugin format — use /plugin install for that.
#   - Configure your MCP API key — you do that manually in your tool's
#     MCP config so the key never touches this script.
#   - Run on Windows native — use WSL or Git Bash.

set -eu

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SKILLS_SRC="${SCRIPT_DIR}/skills"

# --- Parse args -------------------------------------------------------

TOOL="auto"
while [ $# -gt 0 ]; do
    case "$1" in
        --tool)
            TOOL="$2"
            shift 2
            ;;
        --tool=*)
            TOOL="${1#--tool=}"
            shift
            ;;
        -h|--help)
            sed -n '1,30p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            echo "Run with --help for usage." >&2
            exit 2
            ;;
    esac
done

# --- Helpers ----------------------------------------------------------

detect_tools() {
    local found=()
    [ -d "$HOME/.claude" ] && found+=("claude")
    [ -d "$HOME/.codex" ]  && found+=("codex")
    [ -d "$HOME/.gemini" ] && found+=("gemini")
    [ -d "$HOME/.cursor" ] && found+=("cursor")
    printf '%s\n' "${found[@]}"
}

install_to() {
    local tool="$1"
    local dest

    case "$tool" in
        claude)
            cat <<MSG
⚠ Claude Code detected.
This script is NOT the right path for Claude Code. Use the plugin
instead — you get the skills, the MCP connection, and the hooks
all in one command:

    /plugin marketplace add truverifai/claude-plugins
    /plugin install panel-review@truverifai

Skipping Claude Code install. Continuing with other detected tools.
MSG
            return 0
            ;;
        codex)
            dest="$HOME/.codex/skills"
            ;;
        gemini)
            dest="$HOME/.gemini/skills"
            ;;
        cursor)
            dest="$HOME/.cursor/skills"
            ;;
        *)
            echo "Unknown tool: $tool" >&2
            return 1
            ;;
    esac

    mkdir -p "$dest"
    cp -r "${SKILLS_SRC}/." "$dest/"
    echo "✓ Skills copied to $dest"

    case "$tool" in
        cursor)
            cat <<MSG

ℹ Cursor note: Cursor does NOT have native skill auto-discovery yet.
   The skills are installed at ${dest}/ but you'll need to invoke
   them MANUALLY in chat, e.g.:

       /audit-before-commit

   The references/ and examples/ files give Cursor the context it
   needs once you've invoked. Auto-discovery may land in a future
   Cursor release.

MSG
            ;;
        codex|gemini)
            cat <<MSG

ℹ ${tool^} should auto-discover the skills at next launch. Confirm
   by starting a new ${tool} session and asking it to list available
   skills.

MSG
            ;;
    esac

    cat <<MSG
─────────────────────────────────────────────────────────────────
Next step: configure the TruVerifAI MCP server in ${tool}'s MCP
config. The exact path differs per tool but the connection details
are the same:

    URL:        https://mcp.truverif.ai/mcp
    Type:       Streamable HTTP
    Auth:       Authorization: Bearer <YOUR_TVAI_API_KEY>

Generate your tvai_… key at:
    https://truverif.ai/settings/api-keys

Per-tool config reference:
    Codex CLI:  edit ~/.codex/mcp_servers.json (see Codex docs)
    Gemini CLI: edit ~/.gemini/mcp_servers.json (see Gemini docs)
    Cursor:     Settings → Cursor Settings → MCP

─────────────────────────────────────────────────────────────────
MSG
}

# --- Main -------------------------------------------------------------

if [ ! -d "$SKILLS_SRC" ]; then
    echo "ERROR: skills/ directory not found at ${SKILLS_SRC}" >&2
    echo "Run this script from the plugin/ directory." >&2
    exit 1
fi

case "$TOOL" in
    auto)
        TOOLS=( $(detect_tools) )
        if [ ${#TOOLS[@]} -eq 0 ]; then
            cat <<MSG >&2
Could not detect any supported AI coding tool. Looked for:
    ~/.claude  ~/.codex  ~/.gemini  ~/.cursor

Run again with --tool=<codex|gemini|cursor> explicitly, or install
one of the supported tools first.
MSG
            exit 1
        fi
        echo "Detected tools: ${TOOLS[*]}"
        for t in "${TOOLS[@]}"; do
            echo ""
            echo "▶ Installing to ${t}..."
            install_to "$t"
        done
        ;;
    all)
        TOOLS=( codex gemini cursor )
        for t in "${TOOLS[@]}"; do
            echo ""
            echo "▶ Installing to ${t}..."
            install_to "$t"
        done
        ;;
    claude|codex|gemini|cursor)
        install_to "$TOOL"
        ;;
    *)
        echo "Unknown tool: $TOOL" >&2
        echo "Valid: claude, codex, gemini, cursor, all, auto" >&2
        exit 2
        ;;
esac

echo ""
echo "Done. Documentation: https://truverif.ai/docs/mcp"
