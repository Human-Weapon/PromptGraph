"""Structured requirement extraction from messy textual explanations."""

from __future__ import annotations

import re

from .exceptions import RequirementValidationError
from .models import Priority, Requirement, RequirementType

# Heuristics to classify requirement intent from sentence patterns.
# ORDER MATTERS: specific categories (security, constraint, non_functional, business)
# are checked BEFORE the generic functional pattern, because phrases like
# "must encrypt" or "must not log" contain the generic "must" keyword but carry
# a more specific semantic intent.
_TYPE_PATTERNS: list[tuple[re.Pattern[str], RequirementType]] = [
    # --- Specific categories first ---
    (
        re.compile(
            r"\b(secure|security|auth\w*|encrypt|token|key|password|credential|permission|role)\b",
            re.I,
        ),
        RequirementType.SECURITY,
    ),
    (
        re.compile(r"\b(must not|shall not|never|no|deny|restrict|forbid)\b", re.I),
        RequirementType.CONSTRAINT,
    ),
    (
        re.compile(
            r"\b(performance|performant|latency|speed|fast|scalable|efficient"  # noqa: E501
            r"|reliable|available|uptime|respond\w*|response time)\b",
            re.I,
        ),
        RequirementType.NON_FUNCTIONAL,
    ),
    (
        re.compile(r"\b(business|revenue|cost|market|customer|user value|roi)\b", re.I),
        RequirementType.BUSINESS,
    ),
    # --- Generic functional last ---
    (
        re.compile(r"\b(must|should|shall|will|need to|requires?|support|allow|enable)\b", re.I),
        RequirementType.FUNCTIONAL,
    ),
]

_PRIORITY_PATTERNS: list[tuple[re.Pattern[str], Priority]] = [
    (
        re.compile(r"\b(critical|security|data loss|data loss prevention|must never)\b", re.I),
        Priority.P0,
    ),
    (
        re.compile(r"\b(broken|blocked|cannot work|failing|broken functionality)\b", re.I),
        Priority.P1,
    ),
    (re.compile(r"\b(core|essential|main|primary|key capability)\b", re.I), Priority.P2),
    (re.compile(r"\b(tests?|reliab|stability)\b", re.I), Priority.P3),
    (re.compile(r"\b(perf|optim|faster|speed)\b", re.I), Priority.P4),
    (re.compile(r"\b(experience|dx|cli|docs?|usability)\b", re.I), Priority.P6),
]

_ANY_PATTERN = re.compile(
    r"\bmust\b|\bshall\b|\bneed\b|\brequires?\b|\bshould\b|\bprovide\b|\bsupport\b|\ballow\b|\benable\b|\bnever\b",
    re.I,
)

_TOP_LEVEL = re.compile(
    r"(?<=[.;:\n!?])\s*|\n\s*(?=[A-Za-z])",
)


def _split_sentences(text: str) -> list[str]:
    """Split a messy explanation into candidate sentences/segments."""
    # Normalize whitespace.
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    # Split on sentence boundaries (period, semicolon, newline markers, questions).
    parts = re.split(r"(?<=[.;!?\n])\s+", text)
    segments: list[str] = []
    for p in parts:
        p = p.strip()
        # Also break on explicit numbered/bullet separators.
        # Only split on standalone bullets (space-dash-space), not intra-word hyphens.
        sub = re.split(r"\s+[•\-]\s+|\s+\d+[.)]\s+", p)
        for s in sub:
            s = s.strip()
            if s:
                segments.append(s)
    return segments


_VAGUE = re.compile(
    r"^(.{0,60}?)\b(etc|and so on|something like that|similar)\b.*$|"  # truncated listings
    r"\b(somehow|some way|as needed|appropriately|eventually|later on)\b",
    re.I,
)


def _is_actionable(segment: str) -> bool:
    """Heuristic: a segment is actionable if it expresses an imperative/requirement."""
    if len(segment) < 6:
        return False
    return bool(_ANY_PATTERN.search(segment))


def _is_vague(segment: str) -> bool:
    """Heuristic: detect vagueness markers that need a clarifying question."""
    return bool(_VAGUE.search(segment))


def _is_substantive(segment: str) -> bool:
    """Heuristic: a segment is substantive if it has meaningful content.

    Used to preserve non-English or stylistically different input rather
    than silently dropping it (PG-06).  A segment is substantive if it
    has at least 10 characters and contains word-like tokens (letters
    from any script, or CJK characters).
    """
    stripped = segment.strip()
    if len(stripped) < 10:
        return False
    # Check for CJK characters, Cyrillic, Arabic, or general word patterns.
    # This is intentionally permissive — we'd rather surface than drop.
    if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\u0400-\u04ff\u0600-\u06ff]", stripped):
        return True  # CJK / Cyrillic / Arabic script detected
    # At least 3 word-like tokens of length >= 2.
    tokens = re.findall(r"[a-zA-Z\u00C0-\u024F]{2,}", stripped)
    return len(tokens) >= 3


def classify_type(description: str) -> RequirementType:
    """Classify a requirement description into a RequirementType."""
    lowered = description.lower()
    for pattern, ttype in _TYPE_PATTERNS:
        if pattern.search(lowered):
            return ttype
    return RequirementType.UNKNOWN


def classify_priority(description: str) -> Priority:
    """Classify priority from keywords, defaulting to P2."""
    lowered = description.lower()
    for pattern, prio in _PRIORITY_PATTERNS:
        if pattern.search(lowered):
            return prio
    return Priority.P2


class RequirementExtractor:
    """Extracts structured requirements from messy user explanations.

    This is intentionally rule-based and dependency-free. In production it could
    be backed by an LLM; this module defines a deterministic baseline that works
    standalone.
    """

    def __init__(self, min_length: int = 6) -> None:
        self.min_length = min_length

    def extract(self, explanation: str) -> list[Requirement]:
        """Split a messy explanation into structured requirements.

        Returns a list of requirements. Ambiguous/vague segments are returned
        with a flag (via tags) so PromptGraph can ask targeted questions.

        PG-06 fix: Segments that contain substantive content but don't match
        any English imperative keyword are preserved as UNKNOWN requirements
        (tagged 'low_confidence' and 'possibly_non_english') rather than
        silently dropped.  This ensures multilingual input is surfaced for
        the user to review.
        """
        if not isinstance(explanation, str) or not explanation.strip():
            raise RequirementValidationError("Explanation must be a non-empty string.")

        segments = _split_sentences(explanation)
        requirements: list[Requirement] = []
        counter = 0

        for segment in segments:
            description = segment.strip()
            if _is_actionable(segment):
                rtype = classify_type(description)
                prio = classify_priority(description)
                tags: list[str] = []
                if _is_vague(description):
                    tags.append("needs_clarification")
                counter += 1
                requirements.append(
                    Requirement(
                        id=f"R{counter}",
                        description=description,
                        requirement_type=rtype,
                        priority=prio,
                        source=segment,
                        tags=tags,
                    )
                )
            elif _is_substantive(segment):
                # PG-06: Preserve substantive segments that don't match
                # English imperative patterns. These may be non-English
                # or stylistically different. Surface them as UNKNOWN.
                counter += 1
                requirements.append(
                    Requirement(
                        id=f"R{counter}",
                        description=description,
                        requirement_type=RequirementType.UNKNOWN,
                        priority=Priority.P2,
                        source=segment,
                        tags=["low_confidence", "possibly_non_english"],
                    )
                )
        return requirements

    def extract_preserving_all(self, explanation: str) -> list[Requirement]:
        """Extract requirements keeping even weakly-actionable segments, but t
        agging low-confidence ones for QuestionBudget."""
        base = self.extract(explanation)
        out: list[Requirement] = []
        for req in base:
            extra_tags = list(req.tags)
            if req.requirement_type is RequirementType.UNKNOWN:
                extra_tags.append("low_confidence")
            # shallow copy for cleanliness
            out.append(_with_tags(req, extra_tags))
        return out


def _with_tags(req: Requirement, tags: list[str]) -> Requirement:
    import copy

    r = copy.copy(req)
    r.tags = list(tags)
    return r
