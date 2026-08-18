#!/usr/bin/env node
// OS-neutral gate launcher. Node is the one runtime guaranteed wherever an
// npm-installed host (Codex) runs, and `node <script>` is the canonical hook
// command form in Codex's own docs — no bash/cmd dependency, so a Windows
// machine whose only `bash` is WSL's (which can't read C:\ paths) still works.
//
//   usage: node run_gate.js <host> <gate_script.py>
//   - read the interpreter recorded at install time
//   - set TVAI_PLATFORM=<host>
//   - pipe stdin through to the gate, print its stdout (the decision JSON)
//   - ALWAYS exit 0: a deny is JSON, never an exit code; a crash or missing
//     python fails OPEN (the product-wide invariant).
//
// THE RULE THIS FILE EXISTS TO ENFORCE (roadmap 1.1):
// **A hook never searches for an interpreter in its own process.**
//
// It used to. It probed py/python3/python on EVERY tool call, and on Windows
// that probe can kill the process outright — `python3` there is usually the
// Microsoft Store alias stub, spawning it poisons libuv's global job handle,
// and the next spawn calls uv_fatal_error -> abort(). That abort happens below
// JavaScript: the try/catch at the bottom of this file cannot catch it and
// never could. An external user ran with zero gate coverage for the entire life
// of their install and nothing said so (X13, 2026-08-17).
//
// So: the interpreter is resolved ONCE, at install time, and recorded. This
// file reads that record and launches it. When the record goes stale — someone
// upgrades Python — repair happens in a CHILD process (resolve_python.js), so a
// crash during the search kills the child and this process survives to see a
// non-zero exit. Searching is fine; searching *here* is not.
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

// GUARDED require (adversarial review 2026-08-18, finding A — the worst one).
// This dependency is new this round; the old launcher imported nothing. A
// module-scope `require` sits OUTSIDE the try/catch at the bottom, so a
// missing or corrupt resolve_python.js — an interrupted swap, an antivirus
// quarantine, a torn write — made node exit 1 with MODULE_NOT_FOUND before a
// single line of ours ran. On Copilot CLI a non-zero PreToolUse exit DENIES
// the user's action: the one launcher whose entire contract is "always exit
// 0, fail open" was fail-CLOSED on exactly the machines already in trouble.
// Reproduced: absent sibling -> exit 1; truncated sibling -> exit 1.
let R = null;
try {
  R = require(path.join(__dirname, "resolve_python.js"));
} catch (e) {
  R = null; // main() reports and fails open; exit 0 at the bottom still runs
}

/** Is this recorded interpreter still usable? A file check, never a launch —
 *  reading a directory entry cannot crash the process. */
function usable(p) {
  try {
    return !!p && fs.statSync(p).isFile();
  } catch (e) {
    return false;
  }
}

/** Repair the record, out of process (1.3).
 *
 *  `resolve_python.js --record` spawns only node children, and each of those
 *  spawns exactly one interpreter, so nothing that can be poisoned is ever
 *  reused. If the repair is killed outright we observe a non-zero exit here and
 *  carry on — the uncatchable crash became a catchable one by being someone
 *  else's.
 *
 *  Rate-limited by mayAttemptRepair(): a machine with no Python at all must not
 *  re-run the whole search on every single tool call. */
/** Hook-side repair budget.
 *
 *  This is a HARD ceiling on how long a user's tool call can wait for us. It is
 *  not the install-time budget (120s): there a human is watching and thoroughness
 *  wins; here a hung repair would freeze someone's editor, and a hook that hangs
 *  is worse than a hook that fails — fail-open means fail, not wait.
 *
 *  30s is sized from the work: three candidates at ~1-3s each on a cold Windows
 *  box behind antivirus, plus the gate-code check, with headroom. It is paid at
 *  most once per invocation, only when the interpreter has actually moved, and
 *  the back-off stops it repeating. If it does expire we fail open and leave the
 *  thorough job to `tvai init`. */
const REPAIR_TIMEOUT_MS = 30000;

function repair() {
  const rec = R.readRecord();
  if (!R.mayAttemptRepair(rec, Date.now())) return null;
  const r = spawnSync(process.execPath, [path.join(__dirname, "resolve_python.js"), "--record", __dirname], {
    encoding: "utf8",
    timeout: REPAIR_TIMEOUT_MS,
    // stdout is CAPTURED, never inherited: the hook's own stdout carries the
    // gate's decision JSON, and anything else appearing there would corrupt the
    // host's parse of it.
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (r.status !== 0) return null;
  const fresh = R.readRecord();
  return fresh && usable(fresh.python) ? fresh.python : null;
}

/** Never give up in silence (1.3). A launcher that just `return`s produces the
 *  SAME outcome as the crash — no gate, no signal — only politely. Every
 *  give-up leaves a reason `tvai doctor` can read, and one stderr line so it is
 *  visible in the moment too. */
function giveUp(reason, detail) {
  try {
    // Do NOT clobber an existing reason. When a repair ran, resolve_python has
    // already recorded the per-candidate detail ("py: not installed; python3:
    // Microsoft Store placeholder"), which is the diagnostic that actually
    // helps; this generic message would replace it with less. A reason file
    // only exists while broken, so "already present" means "we already said
    // why, and it is still true".
    if (R && !R.hasReason()) R.writeReason(reason, detail || "");
  } catch (e) {
    /* best effort */
  }
  try {
    process.stderr.write(
      "TruVerifAI: the gates are NOT running — " + reason +
      ". Fix: npx @truverifai/init@latest\n"
    );
  } catch (e) {
    /* stderr may be closed */
  }
}

/** Mark / clear "this GATE SCRIPT crashes with a healthy interpreter" on the
 *  record (adversarial review 2026-08-18, finding B).
 *
 *  The startedButFailed trigger cannot tell "interpreter died" from "gate
 *  script crashes at runtime" (a bad import inside a gate — gate_lib still
 *  parses, so install-verification passes). First shipped behaviour: repair
 *  runs, SUCCEEDS (python is fine), resets failures to 0, the gate re-runs and
 *  crashes again — and because a successful repair resets the counter, the
 *  back-off never engages. Reproduced: 2 gate executions + 4 extra spawns +
 *  ~600ms on EVERY tool call, forever, invisible to doctor.
 *
 *  The disambiguating signal is the repair itself: interpreter re-verified
 *  healthy AND the retry still died silently => the gate is the problem. Mark
 *  it; later calls skip the pointless repair for that script until the
 *  environment changes, an hour passes, or the script succeeds once. */
const GATE_CRASH_TTL_MS = 60 * 60 * 1000;

function gateCrashActive(rec, script) {
  const gc = rec && rec.gateCrash;
  return !!(gc && gc.script === script &&
            gc.fingerprint === R.envFingerprint() &&
            (Date.now() - (gc.at || 0)) < GATE_CRASH_TTL_MS);
}

function setGateCrash(script) {
  try {
    const rec = R.readRecord() || {};
    rec.gateCrash = { script: script, fingerprint: R.envFingerprint(), at: Date.now() };
    R.writeJsonAtomic(R.recordFile(), rec);
  } catch (e) {
    /* best effort — worst case is one extra repair next call */
  }
}

function clearGateCrash(rec, script) {
  try {
    if (rec && rec.gateCrash && rec.gateCrash.script === script) {
      delete rec.gateCrash;
      R.writeJsonAtomic(R.recordFile(), rec);
    }
  } catch (e) {
    /* best effort */
  }
}

function main() {
  const host = process.argv[2] || "";
  const script = process.argv[3] || "";
  if (!script) return;

  if (!R) {
    // Finding A: the resolver module is missing or unloadable. Everything this
    // file could do next needs it, so this is a give-up — but a LOUD one, and
    // through the fail-open exit, never a module-load crash.
    try {
      process.stderr.write(
        "TruVerifAI: the gates are NOT running — resolve_python.js is missing or "
        + "unreadable beside run_gate.js (a damaged install). "
        + "Fix: npx @truverifai/init@latest\n");
    } catch (e) {
      /* stderr may be closed */
    }
    return;
  }

  const rec = R.readRecord();
  let py = rec && usable(rec.python) ? rec.python : null;

  // Stale (or never recorded) -> repair once, then continue with the new path.
  // Heal-and-continue, not heal-and-defer: letting a single action through
  // ungated every time an interpreter moves is the wrong trade for a product
  // whose whole job is not missing gates. The timeout inside repair() is what
  // keeps that bounded.
  if (!py) {
    py = repair();
    if (!py) {
      const failures = (rec && rec.repair && rec.repair.failures) || 0;
      giveUp(
        failures > 0
          ? "no usable Python found (" + failures + " attempt" + (failures === 1 ? "" : "s") + " so far)"
          : rec && rec.python
            ? "the recorded Python is gone and could not be replaced"
            : "no Python interpreter has been recorded",
        rec && rec.python ? String(rec.python) : ""
      );
      return; // fail OPEN — the agent is never trapped by our own breakage
    }
  }

  let input = "";
  try {
    input = fs.readFileSync(0, "utf8");
  } catch (e) {
    /* no stdin -> empty payload */
  }

  const gate = path.join(__dirname, script);
  const opts = {
    input,
    encoding: "utf8",
    timeout: 120000,
    env: Object.assign({}, process.env, { TVAI_PLATFORM: host }),
  };

  let r = spawnSync(py, [gate], opts);

  // Is the recorded interpreter actually working?
  //
  // TWO shapes of "no", and we used to catch only the first:
  //
  //   r.error            — the launch itself failed (file vanished between our
  //                        check and the spawn, not executable, EACCES).
  //   status != 0 and
  //   nothing on stdout  — it STARTED and then died. A deleted virtualenv, a
  //                        missing libpython, an interpreter of the wrong
  //                        architecture. The existence check passes, the launch
  //                        succeeds, and the gate produces nothing — so without
  //                        this the machine sits permanently ungated and never
  //                        repairs, because nothing ever looked broken.
  //
  // The stdout guard is what keeps this from firing on a genuine gate failure:
  // a gate that ran writes its decision JSON, and a gate that legitimately exits
  // non-zero (gate_selfcheck) still prints its reason first. Silence plus a
  // non-zero exit is the interpreter's signature, not the gate's.
  //
  // Neither retry can be the Windows abort: we launch a recorded ABSOLUTE path,
  // never the Store placeholder. Repair runs at most ONCE per invocation, so
  // this cannot loop.
  const failedSilently = (res) => !res.error && res.status !== 0 && !String(res.stdout || "").trim();
  const startedButFailed = failedSilently(r);

  // Finding B: when a recent repair already proved the interpreter healthy and
  // THIS script still died silently, the script is the problem — repairing
  // again is a pointless double-execution. Relay and get out; the marker
  // expires on env change, on the TTL, or the moment the script succeeds.
  if (startedButFailed && gateCrashActive(rec, script)) {
    if (r.stdout) process.stdout.write(r.stdout);
    if (r.stderr) process.stderr.write(r.stderr);
    return;
  }

  if (r.error || startedButFailed) {
    const why = r.error ? String((r.error && r.error.code) || r.error)
                        : "exited " + r.status + " with no output";
    const fixed = repair();
    if (!fixed) {
      giveUp("the recorded Python could not run the gate", why);
      return;
    }
    r = spawnSync(fixed, [gate], opts);
    if (r.error) {
      giveUp("the gate could not be launched after repair",
             String((r.error && r.error.code) || r.error));
      return;
    }
    if (startedButFailed && failedSilently(r)) {
      // Interpreter re-verified by the repair, and the gate died silently
      // AGAIN: it is the gate. Say so (this is a real outage of one gate),
      // and stop repairing for it.
      setGateCrash(script);
      try {
        R.writeReason("gate script crashes with a healthy interpreter",
                      script + " exited " + r.status + " with no output");
      } catch (e) {
        /* best effort */
      }
      try {
        process.stderr.write(
          "TruVerifAI: " + script + " is crashing (interpreter is healthy) — this "
          + "gate is NOT enforcing. Fix: npx @truverifai/init@latest\n");
      } catch (e) {
        /* stderr may be closed */
      }
    }
  } else if (r.status === 0 && rec && rec.gateCrash && rec.gateCrash.script === script) {
    clearGateCrash(rec, script); // the script works again — lift the suppression
  }

  if (r.stdout) process.stdout.write(r.stdout);
  if (r.stderr) process.stderr.write(r.stderr);
}

try {
  main();
} catch (e) {
  /* fail open */
}
process.exit(0);
