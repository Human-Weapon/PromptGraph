"""ContextPackage — assemble the final context package delivered to an agent.

PG-01: Strict hard budget on final rendered prompt.
NEW-04: system_prompt is rendered into agent-facing prompt and counted.
NEW-02: analysis truncation is visible in prompt and status.
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

    def render_summary(self, package: ContextPackage) -> str:
        """Render the full agent-facing package text."""
        lines: list[str] = []
        lines.append(f"# {package.title}")
        lines.append("")

        system_prompt = package.metadata.get("system_prompt") or ""
        if system_prompt:
            lines.append("## System Instructions")
            lines.append(str(system_prompt))
            lines.append("")

        analysis = package.metadata.get("contradiction_analysis") or {}
        if analysis.get("complete") is False:
            lines.append("## Analysis Notice")
            lines.append(
                "Contradiction analysis was incomplete because the configured "
                "analysis limit was reached. Results may not cover all candidate "
                f"pairs (pair_checks={analysis.get('pair_checks', '?')}, "
                f"max_pair_checks={analysis.get('max_pair_checks', '?')})."
            )
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

    def _mandatory_package(
        self,
        title: str,
        requirements: list[Requirement],
        decisions: list[Decision],
        contradictions: list[Contradiction],
        system_prompt: str,
        analysis_meta: dict,
        status: PackageStatus,
        token_budget: int,
    ) -> ContextPackage:
        pkg = ContextPackage(
            title=title,
            prompt="",
            requirements=list(requirements),
            decisions=list(decisions),
            contradictions=list(contradictions),
            context_nodes=[],
            status=status,
            token_budget=token_budget,
            metadata={
                "system_prompt": system_prompt,
                "contradiction_analysis": analysis_meta,
            },
        )
        pkg.prompt = self.render_summary(pkg)
        return pkg

    def build(
        self,
        title: str,
        requirements: list[Requirement],
        context_nodes: list[ContextNode] | None = None,
        decisions: list[Decision] | None = None,
        contradictions: list[Contradiction] | None = None,
        system_prompt: str = "You are a precise software engineering agent.",
        excluded_nodes: list[ContextNode] | None = None,
        *,
        token_budget: int | None = None,
        analysis_truncated: bool = False,
        pair_checks: int = 0,
        max_pair_checks: int | None = None,
    ) -> ContextPackage:
        # P1-01: per-call hard budget is the single source of truth when provided
        effective_budget = self.token_budget if token_budget is None else token_budget
        if effective_budget < 0:
            raise TokenBudgetError("token_budget must be non-negative.")

        nodes = list(context_nodes or [])
        contras = list(contradictions or [])
        decs = list(decisions or [])
        excluded = list(excluded_nodes or [])

        analysis_meta = {
            "complete": not analysis_truncated,
            "pair_checks": pair_checks,
            "max_pair_checks": max_pair_checks,
        }

        strong = [c for c in contras if c.confidence == "strong"]
        if strong:
            status = PackageStatus.BLOCKED
        elif analysis_truncated:
            status = PackageStatus.ANALYSIS_INCOMPLETE
        elif contras:
            status = PackageStatus.NEEDS_CLARIFICATION
        else:
            status = PackageStatus.READY

        # Mandatory includes system_prompt (NEW-04)
        mandatory = self._mandatory_package(
            title,
            list(requirements),
            decs,
            contras,
            system_prompt,
            analysis_meta,
            status,
            effective_budget,
        )
        mandatory_tokens = estimate_token_count(mandatory.prompt)
        if mandatory_tokens > effective_budget:
            raise BudgetExceededError(
                f"Mandatory package content requires {mandatory_tokens} tokens, "
                f"which exceeds the hard budget of {effective_budget}."
            )

        kept = list(nodes)
        while True:
            package = ContextPackage(
                title=title,
                prompt="",
                context_nodes=kept,
                requirements=list(requirements),
                decisions=decs,
                contradictions=contras,
                status=status,
                token_budget=effective_budget,
                excluded_nodes=excluded + [n for n in nodes if n not in kept],
                metadata={
                    "system_prompt": system_prompt,
                    "contradiction_analysis": analysis_meta,
                },
            )
            package.prompt = self.render_summary(package)
            package.compute_tokens()

            if package.total_tokens <= effective_budget:
                package.budget_exceeded = False
                return package

            if not kept:
                raise BudgetExceededError(
                    f"Rendered package requires {package.total_tokens} tokens, "
                    f"exceeding hard budget {effective_budget}."
                )

            kept.sort(key=lambda n: n.estimate_tokens(), reverse=True)
            dropped = kept.pop(0)
            excluded = list(excluded) + [dropped]

    def to_markdown(self, package: ContextPackage) -> str:
        return self.render_summary(package)
