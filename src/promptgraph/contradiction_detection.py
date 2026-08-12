"""Contradiction detection between structured requirements.

PG-07: confidence levels; intra-requirement detection; phrase variants
  (authenticate/authentication/authenticated). Do NOT hardcode
  "public + authentication" as a contradiction.

PG-11: polarity-group candidate filtering + max_pair_checks bound.
  When limited: analysis_truncated=True on result metadata via detector flag.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import Requirement

# Polarity groups: only compare opposing groups.
# Each entry: (polarity_name, pattern)
_POLARITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("allow", re.compile(r"\b(allow|permit|enabled?)\b", re.I)),
    ("deny", re.compile(r"\b(deny|forbid|disabled|never allow|prohibit)\b", re.I)),
    ("public", re.compile(r"\b(public|open to all|no auth)\b", re.I)),
    ("private", re.compile(r"\b(private)\b", re.I)),
    # NOTE: authentication alone is NOT the opposite of public (PG-07).
    ("readonly", re.compile(r"\b(read-only|read only)\b", re.I)),
    ("writable", re.compile(r"\b(writable|write to|write access|read-write)\b", re.I)),
    ("sync", re.compile(r"\b(synchronous|blocking)\b", re.I)),
    ("async", re.compile(r"\b(asynchronous|non-blocking)\b", re.I)),
    ("delete", re.compile(r"\b(delete|remove|drop)\b", re.I)),
    ("preserve", re.compile(r"\b(preserve|keep|retain)\b", re.I)),
    ("increase", re.compile(r"\b(increase|add|expand)\b", re.I)),
    ("decrease", re.compile(r"\b(decrease|reduce|shrink)\b", re.I)),
]

# Opposing polarity pairs and default confidence
_OPPOSING: list[tuple[str, str, str]] = [
    ("allow", "deny", "heuristic"),
    ("public", "private", "strong"),  # public vs private (NOT public vs auth)
    ("readonly", "writable", "strong"),
    ("sync", "async", "strong"),
    ("delete", "preserve", "heuristic"),
    ("increase", "decrease", "heuristic"),
]

# Intra-requirement opposing phrases (same sentence)
_INTRA_PAIRS: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    (
        re.compile(r"\b(public)\b", re.I),
        re.compile(r"\b(private)\b", re.I),
        "strong",
    ),
    (
        re.compile(r"\b(read-only|read only)\b", re.I),
        re.compile(r"\b(writable|write access)\b", re.I),
        "strong",
    ),
    (
        re.compile(r"\b(allow|permit)\b", re.I),
        re.compile(r"\b(deny|forbid)\b", re.I),
        "heuristic",
    ),
]

DEFAULT_MAX_PAIR_CHECKS = 50_000


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _content_overlap(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass
class Contradiction:
    """A detected contradiction between requirements (or within one)."""

    requirement_a: str
    requirement_b: str
    snippet_a: str
    snippet_b: str
    reason: str = ""
    severity: str = "warning"
    confidence: str = "heuristic"  # strong | heuristic

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


@dataclass
class DetectionResult:
    """Result of contradiction detection with truncation signal."""

    findings: list[Contradiction] = field(default_factory=list)
    analysis_truncated: bool = False
    pair_checks: int = 0


class ContradictionDetector:
    """Detects contradictions with polarity grouping and bounded work."""

    def __init__(
        self,
        overlap_threshold: float = 0.15,
        max_pair_checks: int = DEFAULT_MAX_PAIR_CHECKS,
    ) -> None:
        self.overlap_threshold = overlap_threshold
        self.max_pair_checks = max_pair_checks
        self.last_result: DetectionResult | None = None

    def detect(self, requirements: Iterable[Requirement]) -> list[Contradiction]:
        result = self.detect_with_meta(requirements)
        self.last_result = result
        return result.findings

    def detect_with_meta(self, requirements: Iterable[Requirement]) -> DetectionResult:
        reqs = list(requirements)
        findings: list[Contradiction] = []
        pair_checks = 0
        truncated = False

        # Intra-requirement checks (linear)
        for req in reqs:
            for pa, pb, conf in _INTRA_PAIRS:
                ma, mb = pa.search(req.description), pb.search(req.description)
                if ma and mb:
                    findings.append(
                        Contradiction(
                            requirement_a=req.id,
                            requirement_b=req.id,
                            snippet_a=ma.group(0),
                            snippet_b=mb.group(0),
                            reason=(
                                f"Intra-requirement conflict in {req.id}: "
                                f"'{ma.group(0)}' vs '{mb.group(0)}'"
                            ),
                            severity="warning" if conf == "strong" else "info",
                            confidence=conf,
                        )
                    )

        # Assign polarities
        polarity_map: dict[str, list[tuple[int, Requirement, re.Match[str]]]] = {}
        for idx, req in enumerate(reqs):
            for pname, pat in _POLARITY_PATTERNS:
                m = pat.search(req.description)
                if m:
                    polarity_map.setdefault(pname, []).append((idx, req, m))

        # Compare only opposing groups
        seen_pairs: set[tuple[str, str, str, str]] = set()
        for pol_a, pol_b, default_conf in _OPPOSING:
            group_a = polarity_map.get(pol_a, [])
            group_b = polarity_map.get(pol_b, [])
            if not group_a or not group_b:
                continue
            for _ia, ra, ma in group_a:
                for _ib, rb, mb in group_b:
                    if ra.id == rb.id:
                        continue
                    key = tuple(sorted([ra.id, rb.id]) + [ma.group(0).lower(), mb.group(0).lower()])
                    if key in seen_pairs:
                        continue
                    pair_checks += 1
                    if pair_checks > self.max_pair_checks:
                        truncated = True
                        break
                    overlap = _content_overlap(ra.description, rb.description)
                    conf = default_conf
                    if default_conf == "strong" and overlap < self.overlap_threshold:
                        conf = "heuristic"
                    # For heuristic pairs, require some overlap to reduce FPs
                    if conf == "heuristic" and overlap < 0.05:
                        continue
                    seen_pairs.add(key)
                    findings.append(
                        Contradiction(
                            requirement_a=ra.id,
                            requirement_b=rb.id,
                            snippet_a=ma.group(0),
                            snippet_b=mb.group(0),
                            reason=(
                                f"'{ma.group(0)}' in {ra.id} conflicts with "
                                f"'{mb.group(0)}' in {rb.id}"
                            ),
                            severity="warning" if conf == "strong" else "info",
                            confidence=conf,
                        )
                    )
                if truncated:
                    break
            if truncated:
                break

        return DetectionResult(
            findings=findings,
            analysis_truncated=truncated,
            pair_checks=pair_checks,
        )
