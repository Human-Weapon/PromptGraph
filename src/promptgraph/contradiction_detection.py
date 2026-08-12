"""Contradiction detection between structured requirements.

PG-07 fix: Findings now carry a ``confidence`` field ('strong' or
'heuristic').  Weak lexical matches that may be false positives are
marked ``confidence='heuristic'`` and ``severity='info'``.  Strong
direct antonyms remain ``confidence='strong'``.

Same-requirement detection: if two requirements share significant token
overlap, they are more likely to be about the same subject and thus a
contradiction is more credible.  Disjoint requirements with weak signal
are downgraded.

PG-11 fix: Candidate filtering — requirements that contain NO pattern
keyword at all are excluded from pairwise comparison, reducing the
quadratic constant factor significantly.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Requirement

# Pairs of terms that typically signal contradiction.
# Each pair: (pattern_a, pattern_b, default_confidence)
_CONTRADICTION_PAIRS: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    (
        re.compile(r"\b(read-only|read only)\b", re.I),
        re.compile(r"\b(writable|write to|write access|read-write)\b", re.I),
        "strong",
    ),
    (
        re.compile(r"\b(public|open to all|no auth)\b", re.I),
        re.compile(r"\b(private|auth required|must authenticate)\b", re.I),
        "strong",
    ),
    (
        re.compile(r"\b(synchronous|blocking)\b", re.I),
        re.compile(r"\b(asynchronous|non-blocking)\b", re.I),
        "strong",
    ),
    (
        re.compile(r"\b(allow|permit|enabled?)\b", re.I),
        re.compile(r"\b(deny|forbid|disabled|never allow)\b", re.I),
        "heuristic",
    ),
    (
        re.compile(r"\b(delete|remove|drop)\b", re.I),
        re.compile(r"\b(preserve|keep|retain)\b", re.I),
        "heuristic",
    ),
    (
        re.compile(r"\b(increase|add|expand)\b", re.I),
        re.compile(r"\b(decrease|reduce|shrink)\b", re.I),
        "heuristic",
    ),
]

# Requirements above this size are checked; larger sets use candidate filtering.
_LARGE_SET_THRESHOLD = 200


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _content_overlap(a: str, b: str) -> float:
    """Jaccard similarity of token sets (0.0 to 1.0)."""
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass
class Contradiction:
    """A detected contradiction between two requirements."""

    requirement_a: str
    requirement_b: str
    snippet_a: str
    snippet_b: str
    reason: str = ""
    severity: str = "warning"
    confidence: str = "heuristic"

    def to_dict(self) -> dict[str, object]:
        return {
            "requirement_a": self.requirement_a,
            "requirement_b": self.requirement_b,
            "snippet_a": self.snippet_a,
            "snippet_b": self.snippet_b,
            "reason": self.reason,
            "severity": self.severity,
            "confidence": self.confidence,
        }


class ContradictionDetector:
    """Detects pairwise contradictions among a set of requirements."""

    def __init__(self, overlap_threshold: float = 0.15) -> None:
        self.patterns = _CONTRADICTION_PAIRS
        self.overlap_threshold = overlap_threshold

    def detect(self, requirements: Iterable[Requirement]) -> list[Contradiction]:
        reqs = list(requirements)

        # PG-11: Candidate filtering — only compare requirements that contain
        # at least one pattern keyword. This reduces the constant factor of
        # the O(n²) comparison dramatically for large sets.
        candidates: list[tuple[int, Requirement, list[int]]] = []
        for idx, req in enumerate(reqs):
            matched_pairs: list[int] = []
            for pi, (pa, pb, _) in enumerate(self.patterns):
                if pa.search(req.description) or pb.search(req.description):
                    matched_pairs.append(pi)
            if matched_pairs:
                candidates.append((idx, req, matched_pairs))

        findings: list[Contradiction] = []
        for ii in range(len(candidates)):
            for jj in range(ii + 1, len(candidates)):
                idx_a, a, pairs_a = candidates[ii]
                idx_b, b, pairs_b = candidates[jj]
                common_pairs = set(pairs_a) & set(pairs_b)
                if not common_pairs:
                    continue
                overlap = _content_overlap(a.description, b.description)
                for pi in common_pairs:
                    pat_a, pat_b, default_conf = self.patterns[pi]
                    match_a = pat_a.search(a.description)
                    match_b = pat_b.search(b.description)
                    if match_a and match_b:
                        # Determine confidence: downgrade to heuristic if
                        # requirements have low content overlap (likely
                        # about different subjects).
                        confidence = default_conf
                        if default_conf == "strong" and overlap < self.overlap_threshold:
                            confidence = "heuristic"
                        findings.append(
                            Contradiction(
                                requirement_a=a.id,
                                requirement_b=b.id,
                                snippet_a=match_a.group(0),
                                snippet_b=match_b.group(0),
                                reason=(
                                    f"'{match_a.group(0)}' in {a.id} conflicts with "
                                    f"'{match_b.group(0)}' in {b.id}"
                                ),
                                severity="warning" if confidence == "strong" else "info",
                                confidence=confidence,
                            )
                        )
                        continue
                    # Reverse direction
                    match_a2 = pat_b.search(a.description)
                    match_b2 = pat_a.search(b.description)
                    if match_a2 and match_b2:
                        confidence = default_conf
                        if default_conf == "strong" and overlap < self.overlap_threshold:
                            confidence = "heuristic"
                        findings.append(
                            Contradiction(
                                requirement_a=a.id,
                                requirement_b=b.id,
                                snippet_a=match_a2.group(0),
                                snippet_b=match_b2.group(0),
                                reason=(
                                    f"'{match_a2.group(0)}' in {a.id} conflicts with "
                                    f"'{match_b2.group(0)}' in {b.id}"
                                ),
                                severity="warning" if confidence == "strong" else "info",
                                confidence=confidence,
                            )
                        )
        return findings
