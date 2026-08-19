"""PromptGraph command-line interface.

Uses argparse (stdlib) for a dependency-light CLI.

PG-10 fix: Expected user errors produce concise stderr messages with
stable non-zero exit codes instead of Python tracebacks.  Core APIs
remain exception-based and reusable programmatically.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import PromptGraph
from .exceptions import PromptGraphError
from .memory.host import ProjectMemory
from .memory.models import MemoryCandidate, MemoryType
from .models import Decision


def _json_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true", help="Print only structured JSON.")
    parent.add_argument("--explain", action="store_true", help="Include selection reasons.")
    parent.add_argument("--full", action="store_true", help="Include full technical detail.")
    return parent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promptgraph",
        description=(
            "Transform human intent + project knowledge into precise, efficient agent context."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")
    shared = _json_parent()

    p_prepare = sub.add_parser("prepare", help="Turn a messy explanation into a context package.")
    p_prepare.add_argument("--explanation", "-e", required=True, help="The messy task explanation.")
    p_prepare.add_argument("--title", default="Task context")
    p_prepare.add_argument(
        "--budget",
        type=int,
        default=8000,
        help="Token budget for context (0 = no context nodes).",
    )

    p_lint = sub.add_parser("lint", help="Lint a prompt file or a single prompt string.")
    p_lint.add_argument("--file", "-f", help="Path to a prompt file to lint.")
    p_lint.add_argument("--text", "-t", help="Prompt text to lint.")

    p_q = sub.add_parser("questions", help="Show what questions are needed to fill gaps.")
    p_q.add_argument("--explanation", "-e", required=True)

    p_dec = sub.add_parser("decisions", help="Record or list prior decisions.")
    p_dec.add_argument("--list", action="store_true", help="List all decisions.")
    p_dec.add_argument("--title", help="Decision title (to record).")
    p_dec.add_argument("--decision", help="Decision text.")
    p_dec.add_argument("--context", help="Decision context.")
    p_dec.add_argument("--rationale", help="Decision rationale.")

    sub.add_parser("status", help="Show ecosystem integration status.")

    p_mem = sub.add_parser("memory", help="Persistent project memory.")
    mem_sub = p_mem.add_subparsers(dest="memory_command")

    p_init = mem_sub.add_parser("init", parents=[shared], help="Create a project memory vault.")
    p_init.add_argument("project", nargs="?", default=".")

    p_mstatus = mem_sub.add_parser("status", parents=[shared], help="Show memory vault status.")
    p_mstatus.add_argument("project", nargs="?", default=".")

    p_val = mem_sub.add_parser("validate", parents=[shared], help="Validate project memory.")
    p_val.add_argument("project", nargs="?", default=".")

    p_search = mem_sub.add_parser("search", parents=[shared], help="Search project memory.")
    p_search.add_argument("project", nargs="?", default=".")
    p_search.add_argument("--query", "-q", required=True)
    p_search.add_argument("--area", default="")
    p_search.add_argument("--tag", action="append", default=[])

    p_show = mem_sub.add_parser("show", parents=[shared], help="Show one memory record.")
    p_show.add_argument("project", nargs="?", default=".")
    p_show.add_argument("record_id")

    p_cp = mem_sub.add_parser("checkpoint", parents=[shared], help="Write a session checkpoint.")
    p_cp.add_argument("project", nargs="?", default=".")
    p_cp.add_argument("--goal", required=True)
    p_cp.add_argument("--state", default="")
    p_cp.add_argument("--completed", default="")
    p_cp.add_argument("--remaining", default="")
    p_cp.add_argument("--next", dest="next_task", default="")

    p_rec = mem_sub.add_parser("record", parents=[shared], help="Record structured memory.")
    p_rec.add_argument("project", nargs="?", default=".")
    p_rec.add_argument("--type", required=True)
    p_rec.add_argument("--title", required=True)
    p_rec.add_argument("--body", default="")
    p_rec.add_argument("--area", default="")
    p_rec.add_argument("--tag", action="append", default=[])
    p_rec.add_argument("--scope", default="local_only")
    p_rec.add_argument("--disposition", default="persistent")

    p_plan = mem_sub.add_parser(
        "compact-plan",
        parents=[shared],
        help="Plan compaction of declared context.",
    )
    p_plan.add_argument("project", nargs="?", default=".")
    p_plan.add_argument("--session-id", default="session")
    p_plan.add_argument("--task", default="")
    p_plan.add_argument("--budget", type=int, default=8000)
    p_plan.add_argument("--extraction-complete", action="store_true")
    p_plan.add_argument("--goal", default="")

    p_rebuild = mem_sub.add_parser("rebuild", parents=[shared], help="Rebuild index and graph.")
    p_rebuild.add_argument("project", nargs="?", default=".")

    p_ctx = sub.add_parser("context", help="Build a bounded context package from memory.")
    ctx_sub = p_ctx.add_subparsers(dest="context_command")
    p_build = ctx_sub.add_parser("build", parents=[shared], help="Compile relevant project memory.")
    p_build.add_argument("project", nargs="?", default=".")
    p_build.add_argument("--task", required=True)
    p_build.add_argument("--budget", type=int, default=8000)
    p_build.add_argument("--area", default="")
    p_build.add_argument("--tag", action="append", default=[])
    p_build.add_argument("--path", action="append", default=[])
    p_build.add_argument("--include-local", action="store_true")

    return parser


def _emit_json(payload: Any) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


def _memory(path: str) -> ProjectMemory:
    root = Path(path).resolve()
    return ProjectMemory(root, trusted_root=root)


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


def _cmd_memory(args: argparse.Namespace) -> int:
    if not args.memory_command:
        print(
            "error: choose a memory command (init, status, validate, search, ...)",
            file=sys.stderr,
        )
        return 2
    handlers = {
        "init": _mem_init,
        "status": _mem_status,
        "validate": _mem_validate,
        "search": _mem_search,
        "show": _mem_show,
        "checkpoint": _mem_checkpoint,
        "record": _mem_record,
        "compact-plan": _mem_compact,
        "rebuild": _mem_rebuild,
    }
    return handlers[args.memory_command](args)


def _cmd_context(args: argparse.Namespace) -> int:
    if args.context_command != "build":
        print("error: use `promptgraph context build`", file=sys.stderr)
        return 2
    mem = _memory(args.project)
    pack = mem.build_context_pack(
        args.task,
        budget=args.budget,
        paths=tuple(args.path or []),
        tags=tuple(args.tag or []),
        area=args.area or "",
        include_local=bool(args.include_local),
    )
    payload = pack.to_dict()
    if args.json:
        if not args.explain and not args.full:
            payload.pop("explanations", None)
        return _emit_json(payload)
    print(pack.markdown)
    failures = [i for i in pack.selected_ids if i.startswith("FAIL-")]
    lessons = [i for i in pack.selected_ids if i.startswith("LESSON-")]
    if failures:
        print(f"\n{len(failures)} earlier failures are relevant to this task.")
        print("One previous approach already failed for this reason.")
    if lessons and not failures:
        print(f"{len(lessons)} persistent lessons are relevant to this task.")
    print(
        f"Context package {pack.pack_id}: {pack.total_tokens} tokens (budget {pack.token_budget})."
    )
    if pack.omitted:
        print(f"{pack.omitted} less relevant records were omitted.")
    if args.explain:
        for ident, reasons in pack.explanations.items():
            print(f"{ident} selected because:")
            for reason in reasons:
                print(f"- {reason}")
    return 0


def _mem_init(args: argparse.Namespace) -> int:
    mem = _memory(args.project)
    root = mem.init()
    if args.json:
        return _emit_json({"root": str(root), "initialized": True})
    print(f"Project memory ready at {root}")
    print("You can open that folder as an Obsidian vault if you want a graph view.")
    return 0


def _mem_status(args: argparse.Namespace) -> int:
    status = _memory(args.project).status()
    if args.json:
        return _emit_json(status)
    if not status["exists"]:
        print("No project memory vault yet. Run: promptgraph memory init .")
        return 0
    print(f"Memory records: {status['records']}")
    if status["checkpoint_id"]:
        if status["checkpoint_stale"]:
            print(f"Latest checkpoint {status['checkpoint_id']} is stale.")
        else:
            print("Your latest verified checkpoint is current.")
    else:
        print("No session checkpoint yet.")
    print("Older context can be compacted after the host confirms extraction is complete.")
    return 0


def _mem_validate(args: argparse.Namespace) -> int:
    report = _memory(args.project).validate_memory()
    if args.json:
        return _emit_json(report.to_dict())
    label = "valid" if report.ok else "not fully trusted"
    print(f"Memory {label}: {report.record_count} records")
    print(f"{len(report.unresolved_links)} unresolved links")
    print(f"{len(report.corrupt_records)} corrupt records")
    print("index current" if report.index_current else "index stale or missing")
    if report.contradictions:
        print(f"{len(report.contradictions)} active canonical contradictions")
    return 0 if report.ok or report.status != "analysis_incomplete" else 1


def _mem_search(args: argparse.Namespace) -> int:
    hits = _memory(args.project).search_memory(
        args.query,
        tags=tuple(args.tag or []),
        area=args.area or "",
    )
    if args.json:
        return _emit_json({"hits": [h.to_dict() for h in hits]})
    if not hits:
        print("No relevant memory found.")
        return 0
    failures = [h for h in hits if h.type == "failure"]
    if failures:
        print(f"{len(failures)} earlier failures are relevant to this task.")
    for hit in hits:
        print(f"{hit.record_id}: {hit.title} — {hit.summary}")
        if args.explain:
            for reason in hit.reasons:
                print(f"  - {reason}")
    return 0


def _mem_show(args: argparse.Namespace) -> int:
    record = _memory(args.project).show(args.record_id)
    if args.json:
        return _emit_json(record.to_dict())
    from .memory.serialize import record_to_markdown

    print(record_to_markdown(record), end="")
    return 0


def _mem_checkpoint(args: argparse.Namespace) -> int:
    record = _memory(args.project).checkpoint_session(
        goal=args.goal,
        current_state=args.state,
        completed=args.completed,
        remaining=args.remaining,
        next_task=args.next_task,
    )
    if args.json:
        return _emit_json(record.to_dict())
    print(f"Saved checkpoint {record.id}.")
    print("Your latest verified checkpoint is current.")
    return 0


def _mem_record(args: argparse.Namespace) -> int:
    try:
        mem_type = MemoryType(args.type)
    except ValueError:
        print(f"error: unknown memory type {args.type!r}", file=sys.stderr)
        return 2
    record = _memory(args.project).record_memory(
        MemoryCandidate.from_dict(
            {
                "type": mem_type.value,
                "title": args.title,
                "body": args.body,
                "area": args.area,
                "tags": args.tag,
                "scope": args.scope,
                "disposition": args.disposition,
            }
        )
    )
    if args.json:
        return _emit_json(record.to_dict())
    print(f"Recorded {record.id}: {record.title}")
    return 0


def _mem_compact(args: argparse.Namespace) -> int:
    mem = _memory(args.project)
    checkpoint = None
    if args.goal:
        from .memory.session import checkpoint_candidate_from_kwargs

        checkpoint = checkpoint_candidate_from_kwargs(goal=args.goal)
    manifest = mem.plan_compaction(
        session_id=args.session_id,
        checkpoint=checkpoint,
        task=args.task,
        budget=args.budget,
        extraction_complete=bool(args.extraction_complete),
    )
    if args.json:
        return _emit_json(manifest.to_dict())
    if manifest.safe_to_compact:
        print("Declared context is persisted and verified.")
        print("Older context can be compacted after the host confirms extraction is complete.")
    else:
        print("Not safe to compact declared context.")
        for reason in manifest.reasons:
            print(f"- {reason}")
    return 0


def _mem_rebuild(args: argparse.Namespace) -> int:
    result = _memory(args.project).rebuild()
    if args.json:
        return _emit_json(result)
    print("Rebuilt memory index and graph from Markdown.")
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
        "memory": _cmd_memory,
        "context": _cmd_context,
    }
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
