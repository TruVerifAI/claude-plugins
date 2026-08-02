#!/usr/bin/env node
// OS-neutral gate launcher. Node is the one runtime guaranteed wherever an
// npm-installed host (Codex) runs, and `node <script>` is the canonical hook
// command form in Codex's own docs — no bash/cmd dependency, so a Windows
// machine whose only `bash` is WSL's (which can't read C:\ paths) still works.
//
// Mirrors run_gate.sh / run_gate.cmd exactly:
//   usage: node run_gate.js <host> <gate_script.py>
//   - resolve a working python (py / python3 / python)
//   - set TVAI_PLATFORM=<host>
//   - pipe stdin through to the gate, print its stdout (the decision JSON)
//   - ALWAYS exit 0: a deny is JSON, never an exit code; a crash or missing
//     python fails OPEN (the product-wide invariant).
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

function main() {
  const host = process.argv[2] || "";
  const script = process.argv[3] || "";
  if (!script) return;

  let py = null;
  for (const c of ["py", "python3", "python"]) {
    try {
      const probe = spawnSync(c, ["-c", ""], { stdio: "ignore" });
      if (probe.status === 0) {
        py = c;
        break;
      }
    } catch (e) {
      /* keep probing */
    }
  }
  if (!py) return; // no python -> fail open, silently (parity with run_gate.sh)

  let input = "";
  try {
    input = fs.readFileSync(0, "utf8");
  } catch (e) {
    /* no stdin -> empty payload */
  }

  const gate = path.join(__dirname, script);
  const r = spawnSync(py, [gate], {
    input,
    encoding: "utf8",
    timeout: 120000,
    env: Object.assign({}, process.env, { TVAI_PLATFORM: host }),
  });
  if (r.stdout) process.stdout.write(r.stdout);
  if (r.stderr) process.stderr.write(r.stderr);
}

try {
  main();
} catch (e) {
  /* fail open */
}
process.exit(0);
