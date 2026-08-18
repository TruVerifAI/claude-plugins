#!/usr/bin/env node
// Interpreter resolution for the gates (roadmap Problem 1, fixes 1.1-1.3).
//
// WHY THIS FILE EXISTS
// -------------------
// run_gate.js used to search for a Python interpreter on EVERY tool call, inside
// the process that has to survive. On Windows that search can kill the process
// outright: `python3` there is usually the Microsoft Store App-Execution-Alias
// stub, spawning it poisons libuv's global job handle, and the NEXT spawn calls
// uv_fatal_error -> abort(). That abort is BELOW JavaScript — the try/catch that
// has always wrapped run_gate.js's main() cannot catch it and never could
// (X13, 2026-08-17: an external user had zero gate coverage for the life of
// their install).
//
// So searching moved here, and here it only ever runs:
//   - at install time (`tvai init`), where a crash is visible, or
//   - from a repair helper the hook spawns as a CHILD, where a crash kills the
//     child and the hook survives to see a non-zero exit.
//
// PROCESS TOPOLOGY — the part that makes this safe
// ------------------------------------------------
//   --resolve   drives the search. It spawns ONLY node children, never an
//               interpreter, so it can never be poisoned.
//   --probe X   spawns EXACTLY ONE interpreter and exits. Poisoning kills the
//               *next* spawn, and there is no next spawn, so a probe cannot
//               die of its own poison — and if it dies anyway, it is the only
//               casualty.
//
// Never throws to the caller and never exits non-zero for --resolve on a
// "nothing found" result: the gates fail OPEN, so an unresolvable interpreter
// is a reported condition, not a crash.
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");

// --------------------------------------------------------------------------
// Locations. TVAI_HOME_OVERRIDE is honoured exactly as tvai-cli/lib/config.js
// honours it — every module that touches real user files must resolve home the
// SAME way, or the test sandbox leaks into the real profile.
// --------------------------------------------------------------------------

function homeDir() {
  return (process.env.TVAI_HOME_OVERRIDE || "").trim() || os.homedir();
}

function tvaiDir() {
  return path.join(homeDir(), ".truverifai");
}

/** The interpreter record. One file, JSON, holding the chosen interpreter AND
 *  the repair back-off state — they are written together so a repair can never
 *  update one and lose the other. */
function recordFile() {
  return path.join(tvaiDir(), "python-path.json");
}

/** Why the gates could not start. Written on every give-up so a dead gate is
 *  never silent (1.3); `tvai doctor` reads it. */
function reasonFile() {
  return path.join(tvaiDir(), "gate-failure-reason.json");
}

// --------------------------------------------------------------------------
// Candidates
// --------------------------------------------------------------------------

/** Per-OS order (1.2). The hazards genuinely differ, so the order must too:
 *
 *  Windows — `python3` is usually the Store alias stub, so it goes LAST. `py`
 *  is the official launcher, lives at a fixed location, and is a Python 3
 *  launcher wherever it exists. Python 2 is extinct on Windows.
 *
 *  POSIX — `python` may still be Python 2 (RHEL/CentOS 7, Amazon Linux 2,
 *  Debian with python-is-python2, older container images). That was X6. There
 *  is no App-Execution-Alias concept here, so `python3` first is both safe and
 *  correct. */
function candidates() {
  return process.platform === "win32"
    ? ["py", "python", "python3"]
    : ["python3", "python", "py"];
}

/** Resolve a bare command name to an absolute path by walking PATH ourselves.
 *
 *  Done WITHOUT spawning anything: reading a directory entry cannot crash, and
 *  on Windows it lets us skip a candidate that is not installed without paying
 *  the spawn that might poison the process.
 *
 *  Returns the FIRST match, which is the one the OS would have run. That is
 *  deliberately the *stable* path — `C:\Windows\py.exe`,
 *  `/usr/local/bin/python3` — and NOT `sys.executable`, which reports the
 *  version-specific target (`…/python@3.14/bin/python3.14`) and therefore dies
 *  on the next Python upgrade. Recording the stable path is most of why the
 *  record stays valid (1.1). */
function whichAbs(cmd) {
  const dirs = (process.env.PATH || "").split(path.delimiter).filter(Boolean);
  const exts = process.platform === "win32"
    ? (process.env.PATHEXT || ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)
    : [""];
  for (const d of dirs) {
    for (const ext of exts) {
      const p = path.join(d, cmd + ext);
      try {
        const st = fs.statSync(p);
        if (st.isFile()) return p;
      } catch (e) {
        /* not here; keep looking */
      }
    }
  }
  return null;
}

// --------------------------------------------------------------------------
// --probe: spawn EXACTLY ONE interpreter
// --------------------------------------------------------------------------

/** Exit codes, so the parent can tell the cases apart without parsing text. */
const PROBE_OK = 0;          // usable Python 3; absolute path on stdout
const PROBE_ABSENT = 3;      // not on PATH — nothing was spawned
const PROBE_PLACEHOLDER = 4; // Microsoft Store alias stub (exit 9009)
const PROBE_UNUSABLE = 5;    // ran, but not Python 3
const PROBE_HUNG = 6;        // started and never came back — see below

/** How long ONE interpreter gets to answer "are you Python 3?".
 *
 *  Tight enough that three candidates fit inside the hook-side repair budget,
 *  loose enough for a cold start behind antivirus (1-3s is normal on Windows). */
const PROBE_TIMEOUT_MS = 10000;

/** The Store placeholder's signature. It is a 0-byte reparse point that
 *  redirects to the Store and exits 9009 without ever running Python. A REAL
 *  Microsoft Store Python — a legitimate install we must not break — is
 *  indistinguishable from it on disk but exits 0, so the exit code is the only
 *  honest test (1.2). */
const STORE_PLACEHOLDER_EXIT = 9009;

/** Prints the interpreter's own absolute path, and exits non-zero unless it is
 *  Python 3. One command answers both questions in the single spawn we allow. */
const PROBE_CODE =
  "import sys; " +
  "sys.stdout.write(sys.executable or ''); " +
  "sys.exit(0 if sys.version_info[0] == 3 else 1)";

function probe(cmd) {
  const abs = whichAbs(cmd);

  // Prefer the PATH-walked absolute path, but FALL BACK to the bare name when
  // the walk found nothing (verified on Windows 2026-08-17): Node's fs.stat
  // cannot see an App-Execution-Alias at all — it throws ENOENT even for one
  // CreateProcess resolves happily. That is convenient for the Store
  // PLACEHOLDER (we skip it without spawning), but a GENUINE Microsoft Store
  // Python install presents the same way, and skipping that would report "no
  // Python" on a machine that has a perfectly good one. So when the walk comes
  // up empty we still let the OS try to resolve the name — inside this
  // sacrificial child, where a crash costs only this process.
  const target = abs || cmd;

  // THE one spawn this process is allowed to make.
  const r = spawnSync(target, ["-c", PROBE_CODE], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
    timeout: PROBE_TIMEOUT_MS,
  });

  if (r.error && r.error.code === "ENOENT") return { code: PROBE_ABSENT };
  // A candidate that STARTED and never came back is its own outcome, not "not
  // Python 3". The distinction is load-bearing on macOS: without Xcode command
  // line tools, /usr/bin/python3 is a stub that pops a GUI install dialog and
  // waits for a human who is not there. Reporting that as "not Python 3" would
  // send someone hunting for the wrong problem entirely.
  if (r.error && r.error.code === "ETIMEDOUT") return { code: PROBE_HUNG, abs: target };
  if (r.status === STORE_PLACEHOLDER_EXIT) return { code: PROBE_PLACEHOLDER, abs: target };
  if (r.status === 0) {
    // Record the stable PATH-walked path when we have one; otherwise the
    // interpreter's own report of where it lives.
    const reported = String(r.stdout || "").trim();
    const chosen = abs || reported;
    return chosen ? { code: PROBE_OK, abs: chosen } : { code: PROBE_UNUSABLE, abs: target };
  }
  return { code: PROBE_UNUSABLE, abs: target };
}

// --------------------------------------------------------------------------
// --resolve: drive the probes, one child each
// --------------------------------------------------------------------------

/** Returns {python, tried:[{cmd, outcome}]}. `python` is null when nothing
 *  usable was found — a reported condition, never a throw.
 *
 *  Spawns ONLY node, never an interpreter, so this process cannot be poisoned
 *  no matter what any candidate does. A child killed by the Windows abort shows
 *  up here as an ordinary non-zero exit / signal and we move to the next
 *  candidate — which is the whole point: an uncatchable crash becomes a
 *  catchable one by being someone else's crash. */
function resolve() {
  const tried = [];
  for (const cmd of candidates()) {
    const r = spawnSync(process.execPath, [__filename, "--probe", cmd], {
      encoding: "utf8",
      // A little more than the child's own PROBE_TIMEOUT_MS, so the child gets
      // to report its own timeout (PROBE_HUNG) rather than being killed here
      // and reported as an anonymous signal death.
      timeout: PROBE_TIMEOUT_MS + 5000,
      stdio: ["ignore", "pipe", "ignore"],
    });
    if (r.status === PROBE_OK) {
      const abs = String(r.stdout || "").trim();
      if (abs) {
        tried.push({ cmd: cmd, outcome: "ok" });
        return { python: abs, tried: tried };
      }
      tried.push({ cmd: cmd, outcome: "ok-but-no-path" });
      continue;
    }
    tried.push({
      cmd: cmd,
      outcome:
        r.status === PROBE_ABSENT ? "not installed"
        : r.status === PROBE_PLACEHOLDER ? "Microsoft Store placeholder (exit 9009)"
        : r.status === PROBE_UNUSABLE ? "not Python 3"
        : r.status === PROBE_HUNG ? "started but never responded (on macOS this is usually the Xcode command-line-tools install dialog)"
        // A probe killed by a signal is the SACRIFICIAL CASE working: the child
        // absorbed something fatal — on Windows, plausibly the job-object abort
        // this whole design exists for — and we are still here to try the next
        // candidate. Worth naming so it is recognisable in the wild, since we
        // have never reproduced it.
        : r.signal ? ("probe was killed by " + r.signal + " — the child absorbed a fatal error")
        : ("probe exited " + r.status),
    });
  }
  return { python: null, tried: tried };
}

// --------------------------------------------------------------------------
// Verification: can this interpreter actually run OUR gate code?
// --------------------------------------------------------------------------

/** "Is it Python 3" is weaker than "can it run the gates". A Python 2 that
 *  somehow passed the version check, or a 3.5 too old for our syntax, still
 *  fails here — we hand it gate_lib.py and ask its own parser to read it.
 *
 *  Uses ast.parse rather than importing or compiling: no __pycache__ written,
 *  no import side effects, and a SyntaxError is exactly the signal we want.
 *  Offline, so it runs during install with no network. */
function canRunGateCode(python, gateDir) {
  const target = path.join(gateDir, "gate_lib.py");
  // The path travels as ARGV, never interpolated into the Python source
  // (adversarial review 2026-08-18, finding C): the first version embedded it
  // in an r'…' literal, and a single apostrophe in the path — C:\\Users\\O'Brien
  // — broke the literal, so a perfectly healthy interpreter was recorded as
  // "cannot parse our gate code" and the gates never installed OR self-healed
  // for that user. argv has no quoting semantics to break.
  const code =
    "import ast, io, sys; " +
    "ast.parse(io.open(sys.argv[1], encoding='utf-8').read()); " +
    "sys.exit(0)";
  const r = spawnSync(python, ["-c", code, target], { stdio: "ignore", timeout: PROBE_TIMEOUT_MS });
  return r.status === 0;
}

// --------------------------------------------------------------------------
// The record, and repair back-off
// --------------------------------------------------------------------------

/** A fingerprint of everything that could change the answer. When a repair has
 *  failed and this has not changed, re-running the search will fail the same
 *  way — so this is what lets us retry when something ACTUALLY moved rather
 *  than on a timer (1.3). */
function envFingerprint() {
  // COMPOSITION (documented per audit mcp_5dd6384d F-003): PATH + platform,
  // nothing else. So an interpreter broken IN PLACE (file kept, contents
  // ruined) does not change the fingerprint — a gateCrash marker can then
  // suppress its script's repair for up to the 1h TTL, and a failed repair
  // backs off up to 10 minutes. Bounded and accepted; adding the interpreter
  // file's mtime/size is the backlog upgrade if that window ever bites.
  return crypto.createHash("sha256")
    .update(String(process.env.PATH || "") + "\u0000" + process.platform)
    .digest("hex")
    .slice(0, 16);
}

function readRecord() {
  try {
    const o = JSON.parse(fs.readFileSync(recordFile(), "utf8"));
    return o && typeof o === "object" && !Array.isArray(o) ? o : null;
  } catch (e) {
    return null;
  }
}

/** Write-then-rename: two hooks firing at the same moment must never read a
 *  half-written record. The temp file is in the SAME directory so the rename is
 *  a directory-entry update, not a copy across volumes. */
function writeJsonAtomic(file, obj) {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const tmp = file + ".tmp-" + process.pid;
    fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
    fs.renameSync(tmp, file);
    return true;
  } catch (e) {
    return false;
  }
}

function writeReason(reason, detail) {
  writeJsonAtomic(reasonFile(), {
    reason: reason,
    detail: detail || "",
    at: new Date().toISOString(),
    platform: process.platform,
  });
}

function clearReason() {
  try {
    fs.unlinkSync(reasonFile());
  } catch (e) {
    /* absent is the desired state */
  }
}

/** Is a reason already on record? Callers use this to avoid overwriting a
 *  DETAILED reason with a vaguer one — the resolver's per-candidate list ("py:
 *  not installed; python: not installed; python3: Microsoft Store placeholder")
 *  is the diagnostic that actually helps, and a later generic give-up must not
 *  clobber it. A reason file only exists while broken (recordSuccess clears
 *  it), so "already present" always means "still broken, and we already said
 *  why". */
function hasReason() {
  try {
    return fs.statSync(reasonFile()).isFile();
  } catch (e) {
    return false;
  }
}

const BACKOFF_NORMAL_MS = 10 * 60 * 1000;    // 10 minutes
const BACKOFF_EXHAUSTED_MS = 60 * 60 * 1000; // 1 hour, after repeated failure
const MAX_FAILURES_BEFORE_LONG_BACKOFF = 3;

/** May we attempt a repair right now? Three cheap conditions, ANY of which
 *  permits an attempt (1.3):
 *
 *   1. nothing has failed yet
 *   2. the environment fingerprint changed  -> something really moved, retry now
 *   3. enough time has passed since the last attempt
 *
 *  Without this a machine with no Python at all would re-run the whole search
 *  on every single tool call. */
function mayAttemptRepair(rec, nowMs) {
  if (!rec || !rec.repair) return true;
  const rp = rec.repair;
  if (!rp.failures) return true;
  if (rp.fingerprint !== envFingerprint()) return true;
  const wait = rp.failures >= MAX_FAILURES_BEFORE_LONG_BACKOFF
    ? BACKOFF_EXHAUSTED_MS
    : BACKOFF_NORMAL_MS;
  return (nowMs - (rp.lastAttempt || 0)) >= wait;
}

function recordSuccess(python) {
  // Writes a FRESH record — any gateCrash marker (run_gate.js) is deliberately
  // dropped: a successful repair has just re-verified the interpreter, so
  // re-diagnosing a previously-marked script once is correct, and the bounded
  // cost is one extra diagnostic double-run for it. Same advisory-under-
  // concurrency posture as `failures` (audit mcp_5dd6384d F-005).
  clearReason();
  return writeJsonAtomic(recordFile(), {
    python: python,
    fingerprint: envFingerprint(),
    recordedAt: new Date().toISOString(),
    repair: { failures: 0, lastAttempt: 0, fingerprint: envFingerprint() },
  });
}

function recordFailure(prev, tried, nowMs) {
  const failures = ((prev && prev.repair && prev.repair.failures) || 0) + 1;
  const detail = tried.map((t) => t.cmd + ": " + t.outcome).join("; ");

  // KEEP a previously recorded interpreter if it is still on disk.
  //
  // Repair is not only triggered by "the path is gone" any more — it also fires
  // when the interpreter starts and then fails, which can be transient (a
  // network drive that blinked, an antivirus lock, a half-finished upgrade).
  // Discarding a path that is still present would turn a transient fault into a
  // permanent one: the next hook would have nothing to try and would have to
  // repair from scratch. Keeping it means the next call tries it first and, if
  // the blip has passed, heals for free.
  //
  // Only kept when it still EXISTS — a path we know is gone is worse than none,
  // because it would make the launcher's cheap existence check pass work it
  // cannot do.
  let keep = null;
  try {
    if (prev && prev.python && fs.statSync(prev.python).isFile()) keep = prev.python;
  } catch (e) {
    /* gone — record null */
  }

  writeJsonAtomic(recordFile(), {
    python: keep,
    fingerprint: envFingerprint(),
    recordedAt: new Date().toISOString(),
    // NOTE: `failures` is ADVISORY under concurrency, deliberately. Several
    // hooks can fire at once, all read the same count, and all write back the
    // same increment — so the number can under-count. That is fine and does not
    // need a lock: the writes are atomic, the repair is idempotent, and the
    // only cost of an under-count is one extra repair attempt. A lock here
    // would add a way for the gates to WEDGE, which is far worse than a
    // slightly low counter.
    repair: { failures: failures, lastAttempt: nowMs, fingerprint: envFingerprint() },
  });
  writeReason("no usable Python found", detail);
  // The RECORD keeps `keep` so the next hook can try it. The RETURN says
  // python: null, because this resolve FAILED.
  //
  // Those are different questions and conflating them cost a false green: with
  // `keep` returned as `python`, `--record` exited 0 and `tvai init` printed
  // "✓ python resolved: …" for a run that found nothing and merely declined to
  // erase an old entry. Caught by a negative-control test, which is the entire
  // reason for running them.
  return { python: null, keptPrevious: keep, tried: tried, failures: failures };
}

/** Remove abandoned atomic-write temp files.
 *
 *  writeJsonAtomic writes `<file>.tmp-<pid>` then renames. A process killed
 *  between those two steps leaves the temp behind forever. Swept here rather
 *  than on the hot path: resolution is rare, and this is housekeeping, not
 *  correctness. Age-gated so a temp file belonging to a CONCURRENTLY running
 *  writer is never removed out from under it. */
function sweepTempFiles(nowMs) {
  try {
    const dir = tvaiDir();
    for (const name of fs.readdirSync(dir)) {
      if (!/\.tmp-\d+$/.test(name)) continue;
      const p = path.join(dir, name);
      try {
        if (nowMs - fs.statSync(p).mtimeMs > 5 * 60 * 1000) fs.unlinkSync(p);
      } catch (e) {
        /* raced or busy — next time */
      }
    }
  } catch (e) {
    /* no directory yet, or unreadable — nothing to sweep */
  }
}

/** Resolve, verify against the real gate code, and record. Used by `tvai init`
 *  and by the hook's repair path — ONE implementation, so install-time and
 *  repair-time can never disagree about what a usable interpreter is. */
function resolveAndRecord(gateDir) {
  const now = Date.now();
  sweepTempFiles(now);
  const res = resolve();
  if (!res.python) return recordFailure(readRecord(), res.tried, now);
  if (gateDir && !canRunGateCode(res.python, gateDir)) {
    return recordFailure(readRecord(),
      res.tried.concat([{ cmd: res.python, outcome: "cannot parse our gate code" }]), now);
  }
  recordSuccess(res.python);
  return { python: res.python, tried: res.tried };
}

// --------------------------------------------------------------------------
// CLI
// --------------------------------------------------------------------------

function main() {
  const argv = process.argv.slice(2);
  const mode = argv[0] || "--resolve";

  if (mode === "--probe") {
    const r = probe(argv[1] || "");
    if (r.code === PROBE_OK) process.stdout.write(r.abs);
    process.exit(r.code);
  }

  if (mode === "--record") {
    // gateDir defaults to this file's own directory: the vendored copy and the
    // plugin-bundle copy each verify against the gate code sitting beside them,
    // which is the code that will actually run.
    const out = resolveAndRecord(argv[1] || __dirname);
    process.stdout.write(JSON.stringify(out) + "\n");
    process.exit(out.python ? 0 : 1);
  }

  // --resolve (default): report only, write nothing.
  const out = resolve();
  process.stdout.write(JSON.stringify(out) + "\n");
  process.exit(out.python ? 0 : 1);
}

if (require.main === module) {
  try {
    main();
  } catch (e) {
    // Fail OPEN, and say why. A resolver that crashes must not look like a
    // resolver that found nothing.
    try {
      writeReason("resolver crashed", String((e && e.message) || e).slice(0, 200));
    } catch (e2) {
      /* nothing left to try */
    }
    process.exit(1);
  }
}

module.exports = {
  homeDir, tvaiDir, recordFile, reasonFile,
  candidates, whichAbs, probe, resolve,
  canRunGateCode, envFingerprint,
  readRecord, writeJsonAtomic, writeReason, clearReason, hasReason,
  mayAttemptRepair, recordSuccess, recordFailure, resolveAndRecord,
  PROBE_OK, PROBE_ABSENT, PROBE_PLACEHOLDER, PROBE_UNUSABLE, PROBE_HUNG,
  STORE_PLACEHOLDER_EXIT, PROBE_TIMEOUT_MS, sweepTempFiles,
  BACKOFF_NORMAL_MS, BACKOFF_EXHAUSTED_MS, MAX_FAILURES_BEFORE_LONG_BACKOFF,
};
