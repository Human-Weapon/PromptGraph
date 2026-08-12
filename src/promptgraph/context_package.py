"""ContextPackage — assemble the final context package delivered to an agent.

PG-01 (round 2): Strict hard budget.
  - ONE authoritative token count of the FINAL rendered prompt.
  - Successful packages MUST satisfy total_tokens <= token_budget.
  - If mandatory content cannot fit: raise BudgetExceededError.
  - Never return READY above budget.
"""

from __future__ import annotations

from .contradiction_detection import Contradiction
from .exceptions import BudgetExceededError, TokenBudgetError
from .models import (
    ContextNode,
    ContextPackage,
    Decision,
    PackageStatus,
    Requirement,
    estimate_token_count,
)


class ContextPackageBuilder:
    """Build a ContextPackage from components and render it as a prompt."""

    def __init__(self, token_budget: int = 8000) -> None:
        if token_budget < 0:
            raise TokenBudgetError("token_budget must be non-negative.")
        self.token_budget = token_budget

    def render_summary(
        self,
        package: ContextPackage,
        *,
        include_budget_warning: bool = False,
    ) -> str:
        """Render the package header + requirements + context + decisions.

        By default does NOT include the budget-exceeded footer (that would
        change the token count after the fact).  Warnings are raised as
        exceptions instead of being embedded after counting.
        """
        lines: list[str] = []
        lines.append(f"# {package.title}")
        lines.append("")

        if package.contradictions:
            lines.append("## Contradictions Detected")
            for c in package.contradictions:
                lines.append(
                    f"- [{c.confidence}] {c.reason}"
                    + ("" if c.severity == "info" else f" ({c.severity})")
                )
            lines.append("")

        if package.requirements:
            lines.append("## Requirements")
            for r in package.requirements:
                lines.append(f"- [{r.requirement_type.value}] {r.description}  *(#{r.id})*")
            lines.append("")

        if package.context_nodes:
            lines.append("## Context")
            for n in package.context_nodes:
                lines.append(f"### {n.title}")
                lines.append(n.content)
                lines.append("")
        else:
            lines.append("## Context")
            lines.append("_No additional context nodes selected._")
            lines.append("")

        if package.decisions:
            lines.append("## Prior Decisions")
            for d in package.decisions:
                lines.append(f"- **{d.title}**: {d.decision}")
            lines.append("")

        return "\n".join(lines).strip()

    def _render_mandatory_only(
        self,
        title: str,
        requirements: list[Requirement],
        decisions: list[Decision],
        contradictions: list[Contradiction],
    ) -> str:
        """Render only mandatory structure (no optional context nodes)."""
        stub = ContextPackage(
            title=title,
            prompt="",
            requirements=list(requirements),
            decisions=list(decisions),
            contradictions=list(contradictions),
            context_nodes=[],
            token_budget=self.token_budget,
        )
        return self.render_summary(stub)

    def build(
        self,
        title: str,
        requirements: list[Requirement],
        context_nodes: list[ContextNode] | None = None,
        decisions: list[Decision] | None = None,
        contradictions: list[Contradiction] | None = None,
        system_prompt: str = "You are a precise software engineering agent.",
        excluded_nodes: list[ContextNode] | None = None,
    ) -> ContextPackage:
        """Build a ContextPackage with STRICT token enforcement.

        Mandatory content = title + requirements + decisions + contradictions
        + structural headings.  Optional = context_nodes.

        If mandatory alone exceeds ``token_budget``: ``BudgetExceededError``.
        Optional nodes are greedily kept only while the FINAL rendered prompt
        stays within budget (dropping largest first if needed).
        """
        # system_prompt is accepted and stored in metadata for callers that
        # inject it outside the rendered package body (PG-13).
        nodes = list(context_nodes or [])
        contras = list(contradictions or [])
        decs = list(decisions or [])
        excluded = list(excluded_nodes or [])

        # 1. Check mandatory content alone fits.
        mandatory_text = self._render_mandatory_only(title, list(requirements), decs, contras)
        mandatory_tokens = estimate_token_count(mandatory_text)
        if self.token_budget >= 0 and mandatory_tokens > self.token_budget:
            raise BudgetExceededError(
                f"Mandatory package content requires {mandatory_tokens} tokens, "
                f"which exceeds the hard budget of {self.token_budget}."
            )

        # 2. Fit optional context nodes under remaining budget by iterative drop.
        #    Drop largest nodes first until final render fits.
        kept = list(nodes)
        while True:
            strong = [c for c in contras if c.confidence == "strong"]
            status = (
                PackageStatus.BLOCKED
                if strong
                else (PackageStatus.NEEDS_CLARIFICATION if contras else PackageStatus.READY)
            )
            package = ContextPackage(
                title=title,
                prompt="",
                context_nodes=kept,
                requirements=list(requirements),
                decisions=decs,
                contradictions=contras,
                status=status,
                token_budget=self.token_budget,
                excluded_nodes=excluded + [n for n in nodes if n not in kept],
                metadata={"system_prompt": system_prompt},
            )
            package.prompt = self.render_summary(package)
            package.compute_tokens()

            if package.total_tokens <= self.token_budget:
                package.budget_exceeded = False
                # Strong contradictions block usability even if under budget.
                if strong:
                    package.status = PackageStatus.BLOCKED
                return package

            if not kept:
                # Nothing left to drop but still over — should not happen if
                # mandatory check passed, but guard anyway.
                raise BudgetExceededError(
                    f"Rendered package requires {package.total_tokens} tokens, "
                    f"exceeding hard budget {self.token_budget}."
                )

            # Drop the largest remaining optional node.
            kept.sort(key=lambda n: n.estimate_tokens(), reverse=True)
            dropped = kept.pop(0)
            excluded = list(excluded) + [dropped]

    def to_markdown(self, package: ContextPackage) -> str:
        """Return a standalone markdown document for the package."""
        return self.render_summary(package)
