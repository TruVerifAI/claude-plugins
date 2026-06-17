#!/usr/bin/env bash
# TruVerifAI gate launcher — resolve a WORKING Python and run the named gate
# script ($1), forwarding the PreToolUse JSON on stdin.
#
# Why this exists: hooks.json must not hardcode `python3`. On Windows `python3`
# is the App-Execution-Alias stub (prints "Python was not found", exits 49), so
# a `python3 ...` hook command errors and Claude Code fails OPEN — the gate
# silently no-ops. `"$c" -c ''` actually invokes the interpreter, so the stub
# fails the probe and we fall through to `python`. Fails open (exit 0) if no
# Python is found — the gate must never trap the agent.
DIR="$(cd "$(dirname "$0")" && pwd)"
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c '' >/dev/null 2>&1; then
    exec "$c" "$DIR/$1"
  fi
done
exit 0
