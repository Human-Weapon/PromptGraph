"""ContextPackage — assemble the final context package delivered to an agent.

PG-01 fix: Token budget is enforced.  ``build()`` validates the final
rendered token count against the configured budget and sets
``budget_exceeded`` on the package.  The caller can inspect
``excluded_nodes`` to see what was dropped.

PG-02 fix: Contradictions are propagated to the package.  The package
status (READY / NEEDS_CLARIFICATION / BLOCKED) reflects whether
unresolved strong contradictions exist.
"""

from __future__ import annotations

from .contradiction_detection import Contradiction
from .models import (
    ContextNode,
    ContextPackage,
    Decision,
    PackageStatus,
    Requirement,
)


class ContextPackageBuilder:
    """Build a ContextPackage from components and render it as a prompt."""

    def __init__(self, token_budget: int = 8000) -> None:
        self.token_budget = token_budget

    def render_summary(self, package: ContextPackage) -> str:
        """Render the package header + requirements + context + decisions."""
        lines: list[str] = []
        lines.append(f"# {package.title}")
        lines.append("")

        if package.contradictions:
            lines.append("## ⚠ Contradictions Detected")
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

        if package.budget_exceeded:
            lines.append("## ⚠ Budget Exceeded")
            lines.append(
                f"Rendered content ({package.total_tokens} tokens) exceeds "
                f"the configured budget ({package.token_budget} tokens). "
                f"{len(package.excluded_nodes)} node(s) were excluded."
            )
            lines.append("")

        return "\n".join(lines).strip()

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
        """Build a ContextPackage with token enforcement and contradiction propagation.

        PG-01: The rendered prompt is token-counted once (no double counting).
        If it exceeds ``self.token_budget``, ``budget_exceeded`` is set.
        PG-02: Contradictions are attached to the package and influence status.
        """
        nodes = list(context_nodes or [])
        contras = list(contradictions or [])
        excluded = list(excluded_nodes or [])

        # Determine package status from contradictions.
        strong_conflicts = [c for c in contras if c.confidence == "strong"]
        if strong_conflicts:
            status = PackageStatus.BLOCKED
        elif contras:
            status = PackageStatus.NEEDS_CLARIFICATION
        else:
            status = PackageStatus.READY

        package = ContextPackage(
            title=title,
            prompt=system_prompt,
            context_nodes=nodes,
            requirements=list(requirements),
            decisions=list(decisions or []),
            contradictions=contras,
            status=status,
            token_budget=self.token_budget,
            excluded_nodes=excluded,
        )
        # Render once, then compute tokens from the rendered text.
        package.prompt = self.render_summary(package)
        package.compute_tokens()

        # PG-01: Check if the final rendered package exceeds the budget.
        package.budget_exceeded = self.token_budget > 0 and package.total_tokens > self.token_budget

        return package

    def to_markdown(self, package: ContextPackage) -> str:
        """Return a standalone markdown document for the package."""
        return self.render_summary(package)
