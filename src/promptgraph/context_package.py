"""ContextPackage — assemble the final context package delivered to an agent.

Combines selected context nodes, requirements, and prior decisions into a
single, token-budgeted prompt that an agent can consume directly.
"""

from __future__ import annotations

from .models import ContextNode, ContextPackage, Decision, Requirement


class ContextPackageBuilder:
    """Build a ContextPackage from components and render it as a prompt."""

    def __init__(self, token_budget: int = 8000) -> None:
        self.token_budget = token_budget

    def render_summary(self, package: ContextPackage) -> str:
        """Render the package header + requirements + context + decisions."""
        lines: list[str] = []
        lines.append(f"# {package.title}")
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

    def build(
        self,
        title: str,
        requirements: list[Requirement],
        context_nodes: list[ContextNode] | None = None,
        decisions: list[Decision] | None = None,
        system_prompt: str = "You are a precise software engineering agent.",
    ) -> ContextPackage:
        package = ContextPackage(
            title=title,
            prompt=system_prompt,
            context_nodes=list(context_nodes or []),
            requirements=list(requirements),
            decisions=list(decisions or []),
        )
        package.prompt = self.render_summary(package)
        package.compute_tokens()
        return package

    def to_markdown(self, package: ContextPackage) -> str:
        """Return a standalone markdown document for the package."""
        return self.render_summary(package)
