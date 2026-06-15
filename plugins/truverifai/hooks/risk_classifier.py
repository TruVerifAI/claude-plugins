"""Two-channel deterministic risk classifier for the proactive-invocation gates.

v2 of the classifier (design: docs/MCP/Classifier/risk-trigger-classifier-design.md).
Replaces the v1 keyword/path matcher. Same public contract — `classify_diff()` and
`hunk_content_hash()` are byte-stable so existing receipts keep coverage — with a
superset output (adds `borderline_tier` + per-hunk `signals`).

Key ideas (see the design doc):
- **Declarative config.** All signals/weights/thresholds live in `risk_signals.json`
  (co-located). The engine just compiles + scores. This is the single source of truth;
  `plugin/hooks/risk_classifier.py` + `risk_signals.json` are byte-identical vendored
  copies (scripts/sync_risk_classifier.py; enforced by tests/test_classifier_sync.py).
- **Two channels.** Each signal is `trigger`-class (high-confidence, specific risk) or a
  borderline class (`primitive` / `significance` / `domain`). The *trigger* decision reads
  ONLY the trigger-class sub-score, so borderline-class weight can never promote to a hard
  trigger (the §4.2 cap, by construction). Suppressors apply to the trigger sub-score
  (demote trigger->borderline) but never silence a flagged trigger-class risk (F-007 floor).
- **Removed lines too.** A removed safety control (auth/validation/bounds) scores even when
  the added side is clean — closes the added-lines-only recall blind spot.
- **Borderline sub-tier.** `borderline_tier` ∈ {heavy, lite, None} drives the §6.5
  synthesize soft-gate: Heavy = a genuine *spike* (a borderline signal near a trigger-class
  signal, or significance + domain co-occurrence), never primitive density.

Pure stdlib, no model, no network. Runs server-side (import) AND vendored in the client
hook AND as a CLI:  `git diff --staged | python -m mcp_server.risk_classifier`
"""

import hashlib
import json
import os
import re
import sys
import warnings


HIGH = "high"
LOW = "low"

_TRIGGER_CLASS = "trigger"
_BORDERLINE_CLASSES = ("primitive", "significance", "domain")

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "risk_signals.json")

# Prose/doc files never gate. A design doc / README / changelog that merely *mentions* a
# risky area (the words "session", "authorize", "migration", ...) is a false positive —
# code lives in code files, not the narrative about them. A keyword classifier can't tell
# prose from code, so the only safe move is to not classify prose at all.
_DOC_PATHS = re.compile(r"\.(md|markdown|mdx|rst|adoc|asciidoc)$", re.IGNORECASE)


def _compile_config(cfg):
    signals = []
    for s in cfg["signals"]:
        # auto_trigger is honored ONLY on trigger-class signals (audit F-001): a
        # borderline-class signal can never reach the high band, by construction. If a
        # non-trigger signal is misconfigured with auto_trigger:true we strip it AND warn
        # (audit F-E) so the operator gets feedback instead of a silent demotion.
        auto = bool(s.get("auto_trigger", False))
        if auto and s["class"] != _TRIGGER_CLASS:
            warnings.warn("risk_classifier: auto_trigger ignored on non-trigger signal %r "
                          "(class=%r)" % (s.get("name"), s.get("class")))
            auto = False
        signals.append({
            "name": s["name"],
            "cls": s["class"],
            "category": s["category"],
            "weight": int(s["weight"]),
            "auto": auto,
            "match": s.get("match", "added"),
            "patterns": [re.compile(p) for p in s["patterns"]],
        })
    suppressors = []
    for s in cfg["suppressors"]:
        suppressors.append({
            "name": s["name"],
            "weight": int(s["weight"]),
            "patterns": [re.compile(p) for p in s["patterns"]],
        })
    th = cfg["thresholds"]
    return {
        "signals": signals,
        "suppressors": suppressors,
        "trigger": int(th["trigger"]),
        "borderline_low": int(th["borderline_low"]),
        "version": cfg.get("version", "2"),
    }


def _load(path=_CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as fh:
        return _compile_config(json.load(fh))


# Fail-open config (audit F-004): a malformed / missing risk_signals.json must NEVER
# brick the blocking PreToolUse hook. On any load error we degrade to an empty signal
# set — classify_diff then returns not-risky for everything, so the gate fails open
# (consistent with gate_lib's whole posture). Loud warning so it's not silent.
_EMPTY_CFG = {"signals": [], "suppressors": [], "trigger": 25, "borderline_low": 5, "version": "0-failopen"}

try:
    _CFG = _load()
except Exception as _exc:  # noqa: BLE001 — deliberately broad; this is the fail-open guard
    warnings.warn("risk_classifier: config load failed (%s); failing open (no signals)" % _exc)
    _CFG = dict(_EMPTY_CFG)


# ---------------------------------------------------------------------------
# Hunk hashing — IDENTICAL to v1 (receipts depend on byte-stability). Do not change.
# ---------------------------------------------------------------------------

def hunk_content_hash(lines):
    """Stable, whitespace-tolerant hash of a hunk's content.

    Strip each line's trailing whitespace, drop blank-only lines, join with '\\n',
    sha256, first 16 hex chars. Shared by the classifier and the coverage check so both
    sides agree. (v1-compatible: callers pass the *added* lines; classify_diff falls back
    to the *removed* lines for pure-deletion hunks so they get a distinct hash.)
    """
    norm = [ln.rstrip() for ln in lines]
    norm = [ln for ln in norm if ln.strip() != ""]
    blob = "\n".join(norm)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Diff parsing — yields (path, added_lines, removed_lines) per hunk.
# Hunk boundaries match v1 (one run under each @@), so added-hunk hashes are unchanged.
# ---------------------------------------------------------------------------

def _iter_file_hunks(diff_text):
    path = None
    old_path = None
    added = []
    removed = []
    in_hunk = False
    results = []

    def flush():
        if path and (added or removed):
            results.append((path, list(added), list(removed)))

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            flush()
            added, removed = [], []
            path = None
            old_path = None
            in_hunk = False
            continue
        # File headers `--- `/`+++ ` only appear BEFORE the first @@ of a file, so we
        # match them only when not in a hunk. This is what lets an in-hunk content line
        # that itself starts with `---`/`+++` (a PEM `-----BEGIN ...`, a YAML `---`) be
        # collected as real content instead of mistaken for a header — and a removed
        # whole-file deletion still binds to the a-side path (audit F-003).
        if not in_hunk and line.startswith("--- "):
            p = line[4:].strip()
            if p.startswith("a/"):
                p = p[2:]
            old_path = None if p == "/dev/null" else p
            continue
        if not in_hunk and line.startswith("+++ "):
            # The flush here is redundant after a `diff --git` (which already flushed),
            # but load-bearing for plain `diff -u` input that has no `diff --git`
            # separators — it's the only inter-file boundary in that format.
            flush()
            added, removed = [], []
            p = line[4:].strip()
            if p.startswith("b/"):
                p = p[2:]
            new_path = None if p == "/dev/null" else p
            path = new_path or old_path     # deleted file -> fall back to the a-side path
            continue
        if line.startswith("@@"):
            flush()
            added, removed = [], []
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    flush()
    return results


def _any_match(patterns, lines):
    for pat in patterns:
        for ln in lines:
            if pat.search(ln):
                return True
    return False


def _path_match(patterns, path):
    if not path:
        return False
    norm = path.replace("\\", "/")
    return any(p.search(norm) for p in patterns)


def _classify_hunk(path, added, removed):
    """Return a per-hunk verdict dict, or None if not risky."""
    # POLICY (audit F-003): doc/prose paths are categorically excluded BEFORE any signal
    # or trigger-floor logic — a keyword in a README/design-doc is a false positive, not
    # gated risk. The F-007 floor applies only to non-doc hunks; this is a deliberate
    # carveout, not a hole.
    if path and _DOC_PATHS.search(path):
        return None

    fired = []
    for s in _CFG["signals"]:
        m = s["match"]
        if m == "path":
            hit = _path_match(s["patterns"], path)
        elif m == "removed":
            hit = _any_match(s["patterns"], removed)
        else:  # "added"
            hit = _any_match(s["patterns"], added)
        if hit:
            fired.append(s)

    if not fired:
        return None

    # POLICY (audit F-002): suppressors are path-based exclusions with a DUAL effect, both
    # intentional — (a) added to trigger_score they demote HIGH->LOW (the F-007 floor still
    # keeps a trigger-class signal at >= LOW); (b) added to borderline_score they can silence
    # a borderline-ONLY hunk to PASS (e.g. idiomatic concurrency in tests/). They never
    # silence a trigger-class signal.
    supp = [s for s in _CFG["suppressors"] if _path_match(s["patterns"], path)]
    supp_weight = sum(s["weight"] for s in supp)  # negative

    auto = [s for s in fired if s["auto"]]
    trigger_fired = [s for s in fired if s["cls"] == _TRIGGER_CLASS]
    borderline_fired = [s for s in fired if s["cls"] in _BORDERLINE_CLASSES]

    trigger_score = sum(s["weight"] for s in trigger_fired) + supp_weight
    borderline_score = sum(s["weight"] for s in borderline_fired)

    if auto:
        # POLICY (audit F-001): an auto-trigger signal (e.g. a hardcoded secret) is ALWAYS
        # HIGH, bypassing suppressors by design — a leaked key in a test fixture is still a
        # leaked key. auto is compile-enforced to trigger-class only.
        confidence, cat = HIGH, auto[0]["category"]
        reason = "auto_trigger:" + auto[0]["name"]
    elif trigger_score >= _CFG["trigger"]:
        confidence = HIGH
        cat = max(trigger_fired, key=lambda s: s["weight"])["category"]
        reason = "trigger_score_%d" % trigger_score
    elif trigger_fired:
        # F-007 lower bound: a trigger-class signal present floors the band at BORDERLINE.
        # Suppressors demoted it below the threshold; they cannot silence it to PASS.
        confidence = LOW
        cat = max(trigger_fired, key=lambda s: s["weight"])["category"]
        reason = "trigger_near_miss_%d" % trigger_score
    elif (borderline_score + supp_weight) >= _CFG["borderline_low"]:
        confidence = LOW
        cat = max(borderline_fired, key=lambda s: s["weight"])["category"]
        reason = "borderline_score_%d" % borderline_score
    else:
        return None

    # near_miss: a trigger-class signal fired but landed at LOW (suppressed below the
    # threshold). Note the (intended) semantic — a near-miss *raises* the borderline tier
    # toward Heavy: a change adjacent to real risk deserves the closer look (audit F-F).
    near_miss = bool(trigger_fired and confidence == LOW)
    has_sig = any(s["cls"] == "significance" for s in borderline_fired)
    has_dom = any(s["cls"] == "domain" for s in borderline_fired)
    return {
        "category": cat,
        "confidence": confidence,
        "signals": sorted({s["name"] for s in fired}),
        # Per-hunk spike (audit F-006/F-B): a genuine borderline spike is THIS (LOW) hunk
        # being a near-miss OR significance+domain co-occurring IN THE SAME HUNK. Gated to
        # LOW so a HIGH hunk that happens to carry significance+domain never elevates an
        # unrelated borderline hunk's tier.
        "spike": confidence == LOW and (near_miss or (has_sig and has_dom)),
        # v1-compatible hash basis: hash the ADDED lines (v1 hashed added-only, so every
        # added-bearing hunk keeps its v1 hash). Pure-deletion hunks (new in v2) fall back
        # to the removed lines so they get a distinct, stable hash.
        "content_basis": added if added else removed,
    }


def classify_diff(diff_text):
    """Classify a unified diff. Returns:

        {
          "risky": bool,
          "max_confidence": "high" | "low" | None,
          "borderline_tier": "heavy" | "lite" | None,   # §6.5 synthesize gate
          "hunks": [ {path, content_hash, category, confidence, signals}, ... ],
        }

    Empty / trivial diffs return risky=False with no hunks. `max_confidence` and per-hunk
    {path, content_hash, category, confidence} preserve the v1 contract.
    """
    hunks = []
    any_spike = False

    for path, added, removed in _iter_file_hunks(diff_text or ""):
        verdict = _classify_hunk(path, added, removed)
        if verdict is None:
            continue
        hunks.append({
            "path": path,
            "content_hash": hunk_content_hash(verdict["content_basis"]),
            "category": verdict["category"],
            "confidence": verdict["confidence"],
            "signals": verdict["signals"],
        })
        if verdict["spike"]:
            any_spike = True

    max_conf = None
    if any(h["confidence"] == HIGH for h in hunks):
        max_conf = HIGH
    elif hunks:
        max_conf = LOW

    # Borderline sub-tier (§6.5): only when there's a borderline (low) hunk. Heavy = a
    # genuine per-hunk spike (a near-miss, or significance+domain in one hunk); else Lite.
    # NEVER primitive density.
    borderline_tier = None
    if any(h["confidence"] == LOW for h in hunks):
        borderline_tier = "heavy" if any_spike else "lite"

    return {
        "risky": bool(hunks),
        "max_confidence": max_conf,
        "borderline_tier": borderline_tier,
        "hunks": hunks,
    }


def _main(argv):
    diff_text = sys.stdin.read()
    print(json.dumps(classify_diff(diff_text), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
