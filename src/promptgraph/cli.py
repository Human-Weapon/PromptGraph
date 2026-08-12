"""PromptGraph command-line interface.

Uses argparse (stdlib) for a dependency-light CLI.

PG-10 fix: Expected user errors produce concise stderr messages with
stable non-zero exit codes instead of Python tracebacks.  Core APIs
remain exception-based and reusable programmatically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import PromptGraph
from .exceptions import PromptGraphError
from .models import Decision


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promptgraph",
        description=(
            "Transform human intent + project knowledge into precise, efficient agent context."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    # prepare
    p_prepare = sub.add_parser("prepare", help="Turn a messy explanation into a context package.")
    p_prepare.add_argument("--explanation", "-e", required=True, help="The messy task explanation.")
    p_prepare.add_argument("--title", default="Task context")
    p_prepare.add_argument(
        "--budget",
        type=int,
        default=8000,
        help="Token budget for context (0 = no context nodes).",
    )

    # lint
    p_lint = sub.add_parser("lint", help="Lint a prompt file or a single prompt string.")
    p_lint.add_argument("--file", "-f", help="Path to a prompt file to lint.")
    p_lint.add_argument("--text", "-t", help="Prompt text to lint.")

    # questions
    p_q = sub.add_parser("questions", help="Show what questions are needed to fill gaps.")
    p_q.add_argument("--explanation", "-e", required=True)

    # decisions
    p_dec = sub.add_parser("decisions", help="Record or list prior decisions.")
    p_dec.add_argument("--list", action="store_true", help="List all decisions.")
    p_dec.add_argument("--title", help="Decision title (to record).")
    p_dec.add_argument("--decision", help="Decision text.")
    p_dec.add_argument("--context", help="Decision context.")
    p_dec.add_argument("--rationale", help="Decision rationale.")

    # status
    sub.add_parser("status", help="Show ecosystem integration status.")

    return parser


def _cmd_prepare(args: argparse.Namespace) -> int:
    pg = PromptGraph()
    result = pg.prepare(args.explanation, args.title, budget=args.budget)
    package = result["package"]
    print(package.prompt)
    print("\n---")
    print(
        f"Requirements: {len(result['requirements'])} | "
        f"Contradictions: {len(result['contradictions'])} | "
        f"Missing dimensions: {len(result['missing_dimensions'])} | "
        f"Questions needed: {len(result['questions'])} | "
        f"Tokens: {result['total_tokens']} | "
        f"Status: {result['package_status']}"
    )
    if result["questions"]:
        print("\nClarify these before proceeding:")
        for q in result["questions"]:
            print(f"  - {q}")
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    from .prompt_lint import PromptLinter

    linter = PromptLinter()
    if args.file:
        try:
            text = Path(args.file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
            return 1
    elif args.text:
        text = args.text
    else:
        print("error: provide --file or --text", file=sys.stderr)
        return 2

    issues = linter.lint(text)
    # Also check for contradictions if text has multiple sentences.
    from .requirement_extraction import RequirementExtractor

    reqs = RequirementExtractor().extract(text)
    if reqs:
        contra_issues = linter.lint_requirements([r.description for r in reqs])
        issues.extend(contra_issues)

    if not issues:
        print("No issues detected.")
        return 0
    for issue in issues:
        loc = f"(line {issue.line}) " if issue.line else ""
        print(f"[{issue.severity}] {issue.category}: {loc}{issue.message}")
    errors = [i for i in issues if i.severity == "error"]
    return 1 if errors else 0


def _cmd_questions(args: argparse.Namespace) -> int:
    pg = PromptGraph(max_questions=100)
    reqs = pg.extract_requirements(args.explanation)
    qset = pg.budget_questions(reqs)
    print(pg.question_budgeter.format(qset))
    return 0


def _cmd_decisions(args: argparse.Namespace) -> int:
    pg = PromptGraph()
    if args.list:
        for d in pg.ledger.all():
            print(f"- {d.id}: {d.title} ({d.decision})")
        if not pg.ledger.all():
            print("No decisions recorded.")
        return 0
    if not (args.title and args.decision):
        print("error: to record, provide --title and --decision", file=sys.stderr)
        return 2
    pid = pg.ledger.record(
        Decision(
            id=args.title.strip().lower().replace(" ", "-")[:50],
            title=args.title,
            decision=args.decision,
            context=args.context or "",
            rationale=args.rationale or "",
        )
    )
    print(f"Recorded decision: {pid}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    pg = PromptGraph()
    print("PromptGraph integrations:")
    for name, present in pg.detect_integrations().items():
        print(f"  {name}: {'installed' if present else 'not installed'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "prepare": _cmd_prepare,
        "lint": _cmd_lint,
        "questions": _cmd_questions,
        "decisions": _cmd_decisions,
        "status": _cmd_status,
    }
    # PG-10: catch domain errors, print concise stderr, no traceback.
    try:
        return handlers[args.command](args)
    except PromptGraphError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
