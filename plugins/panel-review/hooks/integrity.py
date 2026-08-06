#!/usr/bin/env python3
"""Gate-code tamper-EVIDENCE self-check (deliberation mcp_516e5fa1, 2026-08-06).

The gate hooks run on the USER's machine, so we CANNOT prevent someone (an agent
via a shell `echo >> gate_lib.py`, or accidental corruption) from editing the
installed gate code — the G13 case. Prevention is impossible (a determined
tamperer can edit this check too; the user is not the adversary — they WANT the
gate). The realistic goal is tamper EVIDENCE: DETECT a modified gate file, WARN
loudly, and FAIL OPEN (never block the user's work).

HOW: build_bundles.py emits `gate_manifest.json` next to this file = {relpath:
{sha256, text}} for every file in the gate folder (recursing into host/). At the
FIRST gate invocation (cached per process; NEVER raises) this rehashes every
manifest-listed file and compares. A missing/mismatched file => tampered.

VERSION-COMPAT (older installs keep working): the manifest ships WITH each
bundle, so old gate code checks its OWN old manifest. A bundle with NO manifest
(pre-2026-08 installs) => this is a silent NO-OP — identical to today's behavior.
An unknown manifest schema version => also a no-op (a future v2 bundle must not
false-alarm old gate code).

LINE ENDINGS (the top false-positive risk): the generator normalizes EOLs on
write (LF for .py/.json, CRLF for .cmd), and git autocrlf / a zip extractor can
re-normalize post-install. So text files are hashed on the LINE-ENDING-
NORMALIZED (LF) form on BOTH build and runtime — an EOL flip can't false-fire.
Binary files (none today) hash raw; the per-file `text` flag carries that
decision forward.

Extra files in the folder (`__pycache__`, editor temps, `.DS_Store`) are
IGNORED — only manifest-listed files are verified — so a stray .pyc can't
false-fire. Response is warn + fail-open only (owner decision 2026-08-06): the
gate never blocks on a tamper finding; it surfaces `gate_integrity` on the
coverage POST for the server dashboard.
"""

import hashlib
import json
import os
import sys
import threading

# Which extensions are hashed on the EOL-NORMALIZED form (all current gate files
# are text). Mirrors build_bundles._TEXT_EXT + _CRLF_EXT so a .cmd shipped as
# CRLF and a .py shipped as LF both hash to their LF-normalized content.
_TEXT_EXTS = {".py", ".json", ".md", ".sh", ".yaml", ".yml", ".txt", ".toml",
              ".cmd", ".bat", ".js", ".ts", ""}

MANIFEST_NAME = "gate_manifest.json"

_lock = threading.Lock()
_checked = False
# States: ok | tampered | corrupt | unknown_version | no_manifest | error | unchecked
_status = "unchecked"
_details = []             # list[str] problem markers, for telemetry

_WARN = (
    "TruVerifAI GATE INTEGRITY WARNING: one or more installed gate files have "
    "been MODIFIED since install — gate behavior is UNVERIFIED and may not be "
    "enforcing. This is not blocking your work. Reinstall a clean copy with "
    "`npx @truverifai/init` (or reinstall the plugin)."
)


def normalize(raw):
    """LF-canonical form: CRLF -> LF, then bare CR -> LF (order matters).
    Identical to the build-time normalization so EOL re-encoding can't
    false-fire the check."""
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _hash_file(path, is_text):
    with open(path, "rb") as fh:
        raw = fh.read()
    return hashlib.sha256(normalize(raw) if is_text else raw).hexdigest()


def _run_check(gates_dir):
    """(status, problems). Never raises — the caller wraps it too, belt+braces."""
    manifest_path = os.path.join(gates_dir, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        return "no_manifest", []          # old install / feature predates it -> no-op
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        # An EXISTING manifest that won't parse => 'corrupt' (audit mcp_4072f771
        # F-003): distinct from 'tampered' so accidental disk corruption (an
        # interrupted install, power loss) is separable from malice in telemetry.
        # Still warns + fails open (something is wrong with the install).
        return "corrupt", ["manifest_unparseable:%s" % str(exc)[:60]]
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return "corrupt", ["manifest_shape"]
    if data.get("version") != 1:
        # A FUTURE schema (v2 bundle checked by older gate code) => forward-compat
        # SILENT no-op, but a DISTINCT state (audit F-004) so a silent downgrade
        # is observable server-side rather than hidden as 'no_manifest'.
        return "unknown_version", []
    files = data.get("files")
    problems = []
    for rel, entry in files.items():
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            problems.append("unsafe_path:%s" % rel)     # cheap traversal guard
            continue
        target = os.path.join(gates_dir, rel.replace("/", os.sep))
        if not os.path.isfile(target):
            problems.append("missing:%s" % rel)
            continue
        try:
            is_text = bool(entry.get("text", True)) if isinstance(entry, dict) else True
            want = entry.get("sha256", "") if isinstance(entry, dict) else ""
            if _hash_file(target, is_text) != want:
                problems.append("modified:%s" % rel)
        except Exception as exc:
            problems.append("unreadable:%s:%s" % (rel, str(exc)[:40]))
    # Extra files in the folder are intentionally ignored (pyc/editor temps).
    return ("tampered", problems) if problems else ("ok", [])


def check_gate_integrity(gates_dir=None):
    """Return 'ok'|'tampered'|'no_manifest'|'error'. Cached after the first call.
    Emits a loud stderr warning ONCE on 'tampered'. NEVER raises, NEVER blocks."""
    global _checked, _status, _details
    with _lock:
        if _checked:
            return _status
        try:
            if gates_dir is None:
                gates_dir = os.path.dirname(os.path.abspath(__file__))
            _status, _details = _run_check(gates_dir)
        except Exception as exc:
            _status, _details = "error", ["check_exception:%s" % str(exc)[:60]]
        # Warn loudly on a modified gate file (tampered) OR a broken manifest
        # (corrupt) — both mean the install is not trustworthy. 'unknown_version'
        # / 'no_manifest' stay SILENT (forward-compat / old install).
        if _status in ("tampered", "corrupt"):
            try:
                sys.stderr.write("\n" + _WARN + "\n")
                if _details:
                    sys.stderr.write("  affected: " + ", ".join(_details[:6])
                                     + (" ..." if len(_details) > 6 else "") + "\n\n")
                sys.stderr.flush()
            except Exception:
                pass  # a stderr failure must never propagate
        _checked = True
        return _status


def integrity_status():
    """The cached status string for the coverage-POST `gate_integrity` field
    ('unchecked' until check_gate_integrity() has run). Never raises."""
    return _status


def integrity_details():
    """Problem markers for telemetry (empty when ok). Never raises."""
    return list(_details)
