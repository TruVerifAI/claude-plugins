"""Deterministic risk classifier for the proactive-invocation gates.

VENDORED COPY of mcp_server/risk_classifier.py — the plugin ships standalone to
end users and cannot import the backend, so the hook bundles this. Keep in sync
with the canonical backend module on changes. Pure stdlib by design.

One classifier, consumed at three points (proactive-invocation-v2-hybrid §6):
the in-loop `audit` commit-gate, the `audit` merge-coverage check, and the
`deliberate` Write-gate. It answers: *which hunks of this change are risky, and
how confident are we?* — keying on diff **content**, not file paths (C8), because
the same file holds both a trivial comment edit and a structural change.

Confidence drives the `deliberate` demotion flag (§11.1): **block** on
`high`-confidence / irreversible forks (schema, migrations, auth, crypto, deps),
**advisory** on `low`-confidence ones.

Pure and dependency-free (stdlib only) so it can run server-side (import) AND be
vendored into the client-side plugin hook and run as a CLI:

    git diff --staged | python -m mcp_server.risk_classifier

prints a JSON result to stdout. <50ms, no model, no network.
"""

import hashlib
import json
import re
import sys


# Confidence tiers. `high` → block by default; `low` → advisory.
HIGH = "high"
LOW = "low"


# Content signals on ADDED lines. Order matters only for category labelling;
# any high-confidence hit makes the hunk high-confidence.
_HIGH_SIGNALS = [
    ("migration_schema", re.compile(
        r"\b(create|alter|drop)\s+table\b"
        r"|\badd\s+column\b|\bdrop\s+column\b"
        r"|\bdb\.Column\b|\bmapped_column\b"
        r"|\bop\.(create_table|drop_table|add_column|drop_column|alter_column)\b"
        r"|\bCREATE\s+INDEX\b|\bFOREIGN\s+KEY\b",
        re.IGNORECASE)),
    ("auth_security", re.compile(
        r"\b(password|passwd|secret|api[_-]?key|bearer|jwt|oauth|session(_id)?"
        r"|login|logout|permission|privilege|\brole\b|require_admin|is_admin"
        r"|authenticate|authoriz|access[_-]?token|refresh[_-]?token)\b"
        r"|@require_admin",
        re.IGNORECASE)),
    ("crypto", re.compile(
        r"\b(encrypt|decrypt|hmac|cipher|fernet|bcrypt|argon2|pbkdf2|scrypt"
        r"|hashlib|secrets\.token|os\.urandom|private[_-]?key)\b",
        re.IGNORECASE)),
]

_LOW_SIGNALS = [
    ("api_route", re.compile(
        r"@\w*\.?(app|bp|router|blueprint)\.(route|get|post|put|delete|patch)"
        r"|@app\.route|\.add_url_rule\(|\bBlueprint\(",
        re.IGNORECASE)),
    ("concurrency", re.compile(
        r"\b(threading\.|ThreadPoolExecutor|asyncio\.|multiprocessing\."
        r"|Lock\(|Semaphore\(|\basync\s+def\b)\b",
        re.IGNORECASE)),
]

# Path signals (secondary). A dependency-manifest edit is high-confidence
# regardless of content; migration dirs reinforce the content signal.
_DEP_MANIFESTS = re.compile(
    r"(^|/)(requirements[^/]*\.txt|package\.json|pnpm-lock\.yaml|yarn\.lock"
    r"|go\.mod|go\.sum|Gemfile(\.lock)?|pyproject\.toml|poetry\.lock"
    r"|Cargo\.(toml|lock)|composer\.json)$",
    re.IGNORECASE)
_MIGRATION_PATH = re.compile(r"(^|/)migrations?/", re.IGNORECASE)
# Prose/doc files never gate. A design doc, README, or changelog that merely
# *mentions* a risky area (the words "session", "authorize", "migration", …) is a
# false positive — code lives in code files, not the narrative about them. Covers
# the markdown/rst/asciidoc family only; NOT .txt (so requirements.txt still hits
# _DEP_MANIFESTS above). A keyword classifier can't tell prose from code, so the
# only safe move is to not classify prose at all.
_DOC_PATHS = re.compile(r"\.(md|markdown|mdx|rst|adoc|asciidoc)$", re.IGNORECASE)


class RiskyHunk:
    """One risky hunk: which file, a stable content hash (for coverage), the
    category that fired, and the confidence tier."""

    __slots__ = ("path", "content_hash", "category", "confidence")

    def __init__(self, path, content_hash, category, confidence):
        self.path = path
        self.content_hash = content_hash
        self.category = category
        self.confidence = confidence

    def to_dict(self):
        return {
            "path": self.path,
            "content_hash": self.content_hash,
            "category": self.category,
            "confidence": self.confidence,
        }


def hunk_content_hash(added_lines):
    """Stable, whitespace-tolerant hash of a hunk's added content.

    Normalizes so cosmetic churn (trailing whitespace, blank lines) does not
    invalidate coverage: strip each line's trailing whitespace, drop
    blank-only lines, join with '\\n', sha256, first 16 hex chars. Shared by
    the classifier and the coverage check so both sides agree.
    """
    norm = [ln.rstrip() for ln in added_lines]
    norm = [ln for ln in norm if ln.strip() != ""]
    blob = "\n".join(norm)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _iter_file_hunks(diff_text):
    """Yield (path, [added_line, ...]) for each hunk in a unified diff.

    Tolerant of `git diff` output. A 'hunk' is the run of lines under one
    `@@ ... @@` header within a file; added lines are those starting with a
    single '+' (excluding the '+++' file header). For a brand-new file the
    whole body is one added hunk.
    """
    path = None
    added = []
    in_hunk = False
    results = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git") or line.startswith("+++ "):
            # New file boundary — flush the previous hunk.
            if path and added:
                results.append((path, added))
                added = []
            if line.startswith("+++ "):
                # +++ b/path/to/file  (or '+++ /dev/null')
                p = line[4:].strip()
                if p.startswith("b/"):
                    p = p[2:]
                path = None if p == "/dev/null" else p
            in_hunk = False
            continue
        if line.startswith("--- "):
            continue
        if line.startswith("@@"):
            if path and added:
                results.append((path, added))
                added = []
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    if path and added:
        results.append((path, added))
    return results


def _classify_hunk(path, added_lines):
    """Return (category, confidence) or None if not risky."""
    # Prose/docs never gate — keyword matches in narrative are false positives.
    if path and _DOC_PATHS.search(path):
        return None

    text = "\n".join(added_lines)

    # Path-based high-confidence: a dependency manifest change.
    if path and _DEP_MANIFESTS.search(path):
        return ("dependency", HIGH)

    in_migration_dir = bool(path and _MIGRATION_PATH.search(path))

    for category, pat in _HIGH_SIGNALS:
        if pat.search(text):
            return (category, HIGH)
    if in_migration_dir and added_lines:
        # Edits inside a migrations dir that didn't hit a content signal are
        # still structural enough to warrant high confidence.
        return ("migration_schema", HIGH)
    for category, pat in _LOW_SIGNALS:
        if pat.search(text):
            return (category, LOW)
    return None


def classify_diff(diff_text):
    """Classify a unified diff. Returns a dict:

        {
          "risky": bool,
          "max_confidence": "high" | "low" | None,
          "hunks": [ RiskyHunk.to_dict(), ... ],
        }

    Empty / trivial diffs return risky=False with no hunks.
    """
    risky = []
    for path, added in _iter_file_hunks(diff_text or ""):
        verdict = _classify_hunk(path, added)
        if verdict is None:
            continue
        category, confidence = verdict
        risky.append(RiskyHunk(path, hunk_content_hash(added), category, confidence))

    max_conf = None
    if any(h.confidence == HIGH for h in risky):
        max_conf = HIGH
    elif risky:
        max_conf = LOW

    return {
        "risky": bool(risky),
        "max_confidence": max_conf,
        "hunks": [h.to_dict() for h in risky],
    }


def _main(argv):
    diff_text = sys.stdin.read()
    print(json.dumps(classify_diff(diff_text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
