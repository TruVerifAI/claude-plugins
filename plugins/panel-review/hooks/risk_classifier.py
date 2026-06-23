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
            # Pattern indices that match against the comment/string-stripped "code
            # skeleton" of a line instead of the raw line (design §4 precision pass):
            # a bare keyword inside prose / JSX text / a string literal / a comment is
            # NOT code and must not fire, while the SAME keyword as a real identifier or
            # call must. Applied ONLY to the listed indices (the bare-keyword unions);
            # every other pattern — and every signal without this key — stays on raw
            # lines. Secret/SQL/import-string patterns deliberately stay raw (they look
            # INSIDE strings), so they are never listed here.
            "skeleton_match": set(int(i) for i in s.get("skeleton_match", [])),
            # Pattern indices that, on a match, additionally require a real-secret-looking
            # quoted value on the line (literature #3 — the generic `key="value"` secret
            # pattern over-fires on $VAR interpolations and placeholders). Recall-safe.
            "value_filter_patterns": set(int(i) for i in s.get("value_filter_patterns", [])),
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
        # True iff any signal opts a pattern into skeleton matching — lets the
        # hot path skip the (regex-heavy) skeleton build entirely when no signal
        # needs it (and keeps the fail-open empty config zero-cost).
        "has_skeleton": any(sig["skeleton_match"] for sig in signals),
        "trigger": int(th["trigger"]),
        "borderline_low": int(th["borderline_low"]),
        "version": cfg.get("version", "2"),
        "large_hunk_added_lines": int(cfg.get("large_hunk_added_lines", 0)),
        "large_hunk_weight": int(cfg.get("large_hunk_weight", 0)),
        # Floor-bounded threshold-override ceiling (F-011): the highest value a user may
        # raise the trigger threshold to. Sits just below the must-fire trigger weights
        # (auth/secrets/migration/removed-guard = 30) so those always fire; the gate can't
        # be silently disabled via the threshold. gate_lib clamps the user value to this.
        "trigger_threshold_ceiling": int(cfg.get("trigger_threshold_ceiling", int(th["trigger"]))),
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

def clamp_threshold(user_value):
    """Floor-bound a user-supplied trigger threshold (F-011, §4.3).

    Returns a threshold clamped to [borderline_low+1, trigger_threshold_ceiling]. The
    ceiling sits just below the must-fire trigger weights so auth/secrets/migration/
    removed-guard always fire and the gate can't be silently disabled by raising the
    threshold. Returns None (→ config default) for a missing/unparseable value.
    """
    if user_value is None or user_value == "":
        return None
    try:
        v = int(user_value)
    except (TypeError, ValueError):
        return None
    lo = _CFG["borderline_low"] + 1
    hi = _CFG["trigger_threshold_ceiling"]
    if hi < lo:
        hi = lo
    return max(lo, min(v, hi))


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


# ---------------------------------------------------------------------------
# Gate self-mutation (§6.1, audit F-005) + the synthesized self-coverage hash.
# A change touching the gate's OWN config/hooks can disable the gate from inside
# (raise the threshold, empty the signal sets, unhook it) — privilege escalation,
# so the gates force a review even when the content classifier finds nothing.
# These live in this vendored module (byte-identical client + server) so the
# client gate and the server receipt writer agree on BOTH detection and the
# self-coverage hash. Moved from gate_lib.py 2026-06-17 (Option 4 deliberation).
# ---------------------------------------------------------------------------

# The gate's release authority, end to end: the client classifier + decision lib + hook
# DRIVERS (weakening a driver disables the gate), AND the server-side files that decide
# coverage / what counts as a releasing receipt (receipt_writer / receipt_coverage /
# gate_skip). A change to any of these can disable the gate from inside, so they're all
# gate-self (Option 4 audit F-003, 2026-06-17). NOTE the broad multi-route file
# mcp_user_routes.py is intentionally NOT here (it carries dozens of unrelated routes);
# its /receipts/check endpoint is protected by PR review + the manual Replit deploy gate.
_GATE_SELF_PATHS = re.compile(
    r"(^|/)(risk_signals\.json|risk_classifier\.py|gate_lib\.py|hooks\.json"
    r"|audit_gate\.py|deliberate_gate\.py"
    r"|receipt_writer\.py|receipt_coverage\.py|gate_skip\.py"
    r"|\.claude-plugin/|\.git/hooks/)",
    re.IGNORECASE,
)


def is_gate_self_mutation(path):
    """True if `path` would modify the gate's own config/hooks (a bypass vector)."""
    if not path:
        return False
    return bool(_GATE_SELF_PATHS.search(path.replace("\\", "/")))


def diff_touches_gate_self(diff_text):
    """True if any file in the diff modifies the gate's own config/hooks."""
    for line in (diff_text or "").splitlines():
        if line.startswith("+++ b/"):
            if is_gate_self_mutation(line[6:].strip()):
                return True
        elif line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            if len(parts) > 1 and is_gate_self_mutation(parts[1].strip()):
                return True
    return False


# Namespace so a synthesized gate-self hash can never collide with — or be satisfied
# by — a normal hunk_content_hash (which is bare hex). The coverage check, the SKIP
# filter, and the deliberate-only-contributes-gate-self rule all key off the NAMESPACE
# (version-agnostic). The construction PREFIX is versioned (audit F-005): bump the
# version if the hashed inputs ever change, so stale receipts mismatch diagnosably
# (and a future migration can recognize both) rather than silently failing coverage.
GATE_SELF_HASH_NAMESPACE = "gself:"
GATE_SELF_HASH_PREFIX = GATE_SELF_HASH_NAMESPACE + "v1:"


def gate_self_coverage_hash(diff_text):
    """Deterministic self-coverage hash for a gate-self change whose CONTENT
    classifies to ZERO risky hunks (a comment, a deleted signal pattern, ...).

    The gate can't bind such a change to a normal hunk hash, so it binds to THIS
    hash; a real audit/deliberate PASS of the same diff writes the same hash into
    the receipt's covered_hunks (receipt_writer), and ONLY that releases the gate —
    never recent_pass, never a SKIP (Option 4, 2026-06-17 deliberation).

    Hashes per-file ADDED/REMOVED lines (sigil-tagged so add != remove; same
    rstrip / drop-blank normalization as hunk_content_hash), restricted to
    gate-self files, stable-sorted by normalized path. NOT the whole diff: context
    lines, `index <sha>` headers and CRLF all differ between the audit-time and
    commit-time diffs, but the per-file +/- content does not. Prefixed with
    GATE_SELF_HASH_PREFIX to namespace it away from hunk_content_hash.

    Byte-identical client (plugin/hooks/) and server (mcp_server/) — both import it
    from this vendored module (sync_risk_classifier.py --check enforces it).

    Limitation (re-audit F-003): a pure rename / mode-only change to a gate-self file has
    no +/- content, so it yields zero segments and a content-insensitive constant hash.
    Such changes are rare and still require a real PASS to release (no bypass), but two of
    them would collide on coverage — accepted as a known edge, not a security gap.
    """
    segments = {}
    for path, added, removed in _iter_file_hunks(diff_text):
        norm_path = (path or "").replace("\\", "/")
        if not _GATE_SELF_PATHS.search(norm_path):
            continue
        tagged = (["+" + ln.rstrip() for ln in added if ln.strip() != ""]
                  + ["-" + ln.rstrip() for ln in removed if ln.strip() != ""])
        if tagged:
            segments.setdefault(norm_path, []).extend(tagged)
    h = hashlib.sha256()
    for p in sorted(segments):
        h.update(("\x00path:" + p + "\x00").encode("utf-8"))
        h.update(("\n".join(segments[p]) + "\n").encode("utf-8"))
    return GATE_SELF_HASH_PREFIX + h.hexdigest()[:40]


# ---------------------------------------------------------------------------
# Secret-value false-positive filter (literature #3 — the recall-SAFE subset of
# the gitleaks / detect-secrets model). Applies ONLY to the hardcoded_secret
# signal's GENERIC `key = "value"` pattern (the one that over-fires); the specific
# key-format patterns (sk_live_, ghp_, AKIA, PEM) are precise and never filtered.
#
# We deliberately ship only filters that CANNOT drop a real secret (audit
# mcp_8ddbcfae found three recall holes in an earlier draft — all fixed here):
#  - sigil interpolation (`${VAR}`, `$(...)`, `{{ }}`, `%(...)s`, `#{}`, `<% %>`) or a
#    whole-value format field (`"{settings.KEY}"`) -> a REFERENCE, not the secret. A
#    real credential never contains a sigil; a bare `{word}` is only treated as a
#    reference when it is the ENTIRE value (so `"Tr0ub4dor{Blue}99"` still fires).
#  - placeholders matched ONLY whole-value or as a START-of-value `word + delimiter`
#    prefix (`your-...`, `changeme_...`) — NEVER a bare substring, since a real token
#    can contain `null`/`your` via a `-`/`/`/`.` delimiter (`"v1.null.xK9..."` is real).
#  - all-filler / single-char-repeated values.
# No entropy floor: a weak real password (`"111122223333"`) is low-entropy but real,
# so an entropy gate would drop it (audit F-001). The repeated-char anchor below
# covers degenerate filler without that recall cost.
# ---------------------------------------------------------------------------

# Interpolation: a sigil anywhere, OR a value that is ENTIRELY a `{...}` format field.
_INTERP_RE = re.compile(r"\$\{|\$\(|\{\{|\}\}|%\([^)]*\)|%[sd]\b|#\{|<%|^\{[^}]{1,60}\}$")
# Backslash-aware quote scan (audit F-004): an escaped quote inside the value must not
# truncate it (`"ab\"cd..."`). Matches `\\.` (any escaped char) or a non-quote char.
_QUOTED_RE = re.compile(r"""(['"])((?:\\.|(?!\1).)*)\1""")
# Placeholder shapes — all anchored (audit F-002): whole-value filler / repeated char /
# bare placeholder word, OR a value that STARTS with a placeholder word + a delimiter.
_PLACEHOLDER_RE = re.compile(
    r"^[xX*.\-_0\s]+$"                                       # all filler chars
    r"|^(.)\1{6,}$"                                          # one char repeated
    r"|^(none|null|undefined|changeme|placeholder|redacted|tbd|todo)$"   # whole-value word
    r"|^(your|my|the|example|sample|dummy|fake|test|placeholder|change[_-]?me|"
    r"replace[_-]?me|insert|enter|put|set)[_-]",             # placeholder-word + delimiter
    re.IGNORECASE,
)

# Don't scan pathological minified lines (audit F-005): a quote-dense line is O(n^2) for
# the backtracking scan. Conservatively treat an over-long line as possibly-real (fires).
_SECRET_LINE_SCAN_CAP = 2000


def _has_real_secret_value(line):
    """True if `line` contains a quoted literal that looks like an ACTUAL secret —
    not a $VAR/sigil interpolation, not an anchored placeholder, not all-filler.
    Recall-safe: returns True for anything that could plausibly be a real credential
    (no entropy floor — a weak real password must still fire)."""
    if len(line) > _SECRET_LINE_SCAN_CAP:
        return True
    for m in _QUOTED_RE.finditer(line):
        v = m.group(2)
        if len(v) < 12:
            continue
        if _INTERP_RE.search(v):
            continue
        if _PLACEHOLDER_RE.search(v):
            continue
        return True
    return False


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


# ---------------------------------------------------------------------------
# Code-skeleton normalization (design §4 precision pass — deliberated 2026-06-23,
# agreement 0.82). Produces a "code skeleton" of a line for the bare-keyword union
# signals ONLY: it blanks the *content* of comments, string literals, and JSX text
# nodes (preserving delimiters / token boundaries) so a keyword that is prose — a
# marketing string, a JSX label, a comment — disappears, while the SAME keyword used
# as a real identifier or call (outside any quote/comment) survives unchanged. This
# cuts the dominant false-positive class (keyword-in-prose hard-walls) at ZERO recall
# loss on executable code.
#
# Guards (each a deliberation finding):
#  - Interpolated literals are kept RAW: a Python f-string with `{...}` and a JS
#    template literal with `${...}` are left untouched, so `f"...{session}"` /
#    `` `SELECT ${role}` `` keep their keyword. Only non-interpolated literals are
#    blanked (those are UI/log strings).
#  - Only patterns listed in a signal's `skeleton_match` use the skeleton; the
#    hardcoded-secret, SQL, and import-string patterns match the RAW line (they look
#    INSIDE strings — skeletonizing would blind them).
#  - `--` is intentionally NOT treated as a comment (it is JS/C decrement); `#` is a
#    comment only when not preceded by `.`/word char (so JS private fields `this.#x`
#    are not stripped). These keep the skeleton from ever eating real code.
# ---------------------------------------------------------------------------

# One alternation over the lexical regions we blank. Order matters: a `#`/`//` inside
# a string is consumed by the string branch first (earlier start position), so it is
# not mistaken for a comment.
_SK_TOKEN = re.compile(
    r"(?P<lc>//[^\n]*|(?<![\w.])#[^\n]*)"             # line comments (// , bare #)
    r"|(?P<bc>/\*.*?\*/)"                              # inline /* ... */ block comment
    r"|(?P<tmpl>`(?:\\.|[^`\\])*`)"                    # JS/TS template literal
    r"|(?P<str>(?P<pre>[A-Za-z]{0,3})(?P<q>['\"])(?:\\.|(?!(?P=q)).)*(?P=q))"  # quoted string (opt. f/r/b prefix)
)

# A JSX text node: the text between an element's opening `>` and its CLOSING tag `</`.
# Applied ONLY in .jsx/.tsx files (audit F-002) — elsewhere `a > x < b` is a comparison.
# Requiring the trailing `<` to begin a closing tag (`</`) — not just any `<` — is what
# distinguishes `<p>Login</p>` (real text node) from a compact comparison `a>role<b`
# (audit F-A): the latter has `<b`, not `</`, so `role` is never blanked. The lookbehind
# keeps `>` tag-adjacent (preceded by a word / quote / `}` attr-expr / `/`). Real
# marketing-copy FPs are all `>text</tag>`, so this loses no FP coverage.
_SK_JSX_TEXT = re.compile(r"(?<=[\w\"'}/])>([^<>{}]+)<(?=/)")


def _sk_blank(m):
    if m.group("lc") is not None or m.group("bc") is not None:
        return " "
    t = m.group("tmpl")
    if t is not None:
        return t if "${" in t else "``"          # keep interpolated template raw
    s = m.group("str")
    if s is not None:
        pre = m.group("pre") or ""
        q = m.group("q")
        if "f" in pre.lower() and "{" in s:
            return s                               # keep interpolated f-string raw
        return pre + q + q                         # blank content, keep prefix+delimiters
    return m.group(0)


def _code_skeleton(line, in_block, is_jsx):
    """Return (skeleton, in_block) for one line. `in_block` carries multi-line
    block-comment state across the lines of a hunk. `is_jsx` enables JSX-text-node
    blanking — only safe in .jsx/.tsx, since in other languages `>x<` is a comparison
    (`a > x < b`), not a tag boundary (audit F-002)."""
    if in_block:
        close = line.find("*/")
        if close == -1:
            return "", True                        # whole line still inside /* ... */
        line = line[close + 2:]                     # inside a comment, string syntax is inert
        in_block = False
    # Blank comments/strings/templates FIRST, so a `/*` that lives *inside a string*
    # is already gone before we look for an unterminated block comment (audit F-001:
    # scanning the raw line for `/*` would truncate real code after a string literal
    # like "/*", silently dropping a keyword that follows it on the same line).
    s = _SK_TOKEN.sub(_sk_blank, line)
    open_idx = s.find("/*")
    if open_idx != -1 and "*/" not in s[open_idx:]:
        s = s[:open_idx]                            # unterminated /* — drop the tail
        in_block = True
    if is_jsx:
        s = _SK_JSX_TEXT.sub("><", s)
    return s, in_block


def _skeletonize(lines, is_jsx):
    out = []
    in_block = False
    for ln in lines:
        sk, in_block = _code_skeleton(ln, in_block, is_jsx)
        out.append(sk)
    return out


def _signal_hit(patterns, skeleton_idx, value_filter_idx, raw_lines, sk_lines):
    """True if any of `patterns` matches. A pattern whose index is in
    `skeleton_idx` matches against `sk_lines` (the code skeleton); all others
    match against `raw_lines`. A pattern whose index is in `value_filter_idx`
    additionally requires a real-secret-looking quoted value on the matched line
    (literature #3 secret FP filter), else that match is skipped."""
    for i, pat in enumerate(patterns):
        targets = sk_lines if (skeleton_idx and i in skeleton_idx) else raw_lines
        vfilter = bool(value_filter_idx) and i in value_filter_idx
        for ln in targets:
            if pat.search(ln):
                if vfilter and not _has_real_secret_value(ln):
                    continue  # placeholder / $VAR interpolation — not a real secret
                return True
    return False


def _classify_hunk(path, added, removed, trigger_threshold=None):
    """Return a per-hunk verdict dict, or None if not risky.

    `trigger_threshold` overrides _CFG["trigger"] for this call (the floor-bounded
    user override, F-011 — clamped by the caller in gate_lib; the engine just honors
    whatever effective threshold it's handed).
    """
    # POLICY (audit F-003): doc/prose paths are categorically excluded BEFORE any signal
    # or trigger-floor logic — a keyword in a README/design-doc is a false positive, not
    # gated risk. The F-007 floor applies only to non-doc hunks; this is a deliberate
    # carveout, not a hole.
    if path and _DOC_PATHS.search(path):
        return None

    threshold = _CFG["trigger"] if trigger_threshold is None else int(trigger_threshold)

    # Build the comment/string-stripped "code skeleton" once per side (only when a
    # signal actually opts a pattern into skeleton matching — else it's free).
    if _CFG.get("has_skeleton"):
        # JSX text-node blanking is scoped to .jsx/.tsx (audit F-002); comment/string
        # blanking is universal (safe in every language).
        is_jsx = bool(path) and path.lower().endswith((".jsx", ".tsx"))
        sk_added = _skeletonize(added, is_jsx)
        sk_removed = _skeletonize(removed, is_jsx)
    else:
        sk_added, sk_removed = added, removed

    fired = []
    for s in _CFG["signals"]:
        m = s["match"]
        if m == "path":
            hit = _path_match(s["patterns"], path)
        elif m == "removed":
            hit = _signal_hit(s["patterns"], s["skeleton_match"],
                              s["value_filter_patterns"], removed, sk_removed)
        else:  # "added"
            hit = _signal_hit(s["patterns"], s["skeleton_match"],
                              s["value_filter_patterns"], added, sk_added)
        if hit:
            fired.append(s)

    fired_names = {s["name"] for s in fired}
    # Double-count guard (design §4.1): a removed line that matches a real risk pattern is
    # the Tier-3 trigger-class `removed_safety_control`; the Tier-4 borderline
    # `removed_generic_conditional` must NOT also count for the same deletion — the
    # trigger-class match wins. Drop the borderline signal when the trigger one fired.
    if "removed_safety_control" in fired_names and "removed_generic_conditional" in fired_names:
        fired = [s for s in fired if s["name"] != "removed_generic_conditional"]

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

    # large_hunk (design Tier 4 §4.1, weight in config): a large added-line hunk that ALSO
    # carries a risk signal is a borderline *significance* amplifier — "this consequential
    # change has blast radius." Implemented as an amplifier (gated on an existing signal),
    # not a standalone, so a big benign refactor doesn't fire (the design's high-fan-in
    # proxy without a cross-file graph). Counts as significance for the §6.5 spike rule.
    large_lines = _CFG.get("large_hunk_added_lines", 0)
    large_weight = _CFG.get("large_hunk_weight", 0)
    is_large_hunk = bool(fired) and large_lines > 0 and len(added) >= large_lines

    trigger_score = sum(s["weight"] for s in trigger_fired) + supp_weight
    borderline_score = sum(s["weight"] for s in borderline_fired) + (large_weight if is_large_hunk else 0)

    if auto:
        # POLICY (audit F-001): an auto-trigger signal (e.g. a hardcoded secret) is ALWAYS
        # HIGH, bypassing suppressors by design — a leaked key in a test fixture is still a
        # leaked key. auto is compile-enforced to trigger-class only.
        confidence, cat = HIGH, auto[0]["category"]
        reason = "auto_trigger:" + auto[0]["name"]
        score = auto[0]["weight"]
    elif trigger_score >= threshold:
        confidence = HIGH
        cat = max(trigger_fired, key=lambda s: s["weight"])["category"]
        reason = "trigger_score_%d" % trigger_score
        score = trigger_score
    elif trigger_fired:
        # F-007 lower bound: a trigger-class signal present floors the band at BORDERLINE.
        # Suppressors demoted it below the threshold; they cannot silence it to PASS.
        confidence = LOW
        cat = max(trigger_fired, key=lambda s: s["weight"])["category"]
        reason = "trigger_near_miss_%d" % trigger_score
        score = trigger_score
    elif (borderline_score + supp_weight) >= _CFG["borderline_low"]:
        confidence = LOW
        cat = max(borderline_fired, key=lambda s: s["weight"])["category"] if borderline_fired else "significance"
        reason = "borderline_score_%d" % borderline_score
        score = borderline_score + supp_weight
    else:
        return None

    # near_miss: a trigger-class signal fired but landed at LOW (suppressed below the
    # threshold). Note the (intended) semantic — a near-miss *raises* the borderline tier
    # toward Heavy: a change adjacent to real risk deserves the closer look (audit F-F).
    near_miss = bool(trigger_fired and confidence == LOW)
    has_sig = is_large_hunk or any(s["cls"] == "significance" for s in borderline_fired)
    has_dom = any(s["cls"] == "domain" for s in borderline_fired)
    signal_names = sorted({s["name"] for s in fired} | ({"large_hunk"} if is_large_hunk else set()))
    return {
        "category": cat,
        "confidence": confidence,
        "signals": signal_names,
        "score": score,
        "reason": reason,
        "suppressed": sorted(s["name"] for s in supp),
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


def classify_diff(diff_text, trigger_threshold=None):
    """Classify a unified diff. Returns:

        {
          "risky": bool,
          "score": int,                                  # max deciding score across hunks
          "max_confidence": "high" | "low" | None,
          "trigger_reason": str | None,                  # reason of the deciding hunk
          "risk_categories": [str, ...],                 # union across hunks
          "suppressed_by": [str, ...],                   # union of suppressors applied
          "classifier_version": str,
          "borderline_tier": "heavy" | "lite" | None,   # §6.5 synthesize gate
          "hunks": [ {path, content_hash, category, confidence, signals}, ... ],
        }

    Empty / trivial diffs return risky=False with no hunks. `max_confidence` and per-hunk
    {path, content_hash, category, confidence} preserve the v1 contract; the additive
    fields (`score`, `trigger_reason`, `risk_categories`, `suppressed_by`,
    `classifier_version`) feed telemetry + the skip-log training signal (design §4.4, §5.3).
    `trigger_threshold` is the floor-bounded user override (F-011), None = config default.
    """
    hunks = []
    verdicts = []
    any_spike = False

    for path, added, removed in _iter_file_hunks(diff_text or ""):
        verdict = _classify_hunk(path, added, removed, trigger_threshold=trigger_threshold)
        if verdict is None:
            continue
        verdicts.append(verdict)
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

    # The "deciding" hunk drives trigger_reason/score: prefer a HIGH hunk (the one that
    # actually walls), else the highest-scoring borderline hunk.
    deciding = None
    if verdicts:
        high_v = [v for v in verdicts if v["confidence"] == HIGH]
        deciding = max(high_v or verdicts, key=lambda v: v["score"])

    return {
        "risky": bool(hunks),
        "score": deciding["score"] if deciding else 0,
        "max_confidence": max_conf,
        "trigger_reason": deciding["reason"] if deciding else None,
        "risk_categories": sorted({h["category"] for h in hunks}),
        "suppressed_by": sorted({s for v in verdicts for s in v["suppressed"]}),
        "classifier_version": _CFG.get("version", "0"),
        "borderline_tier": borderline_tier,
        "hunks": hunks,
    }


def _main(argv):
    diff_text = sys.stdin.read()
    print(json.dumps(classify_diff(diff_text), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
