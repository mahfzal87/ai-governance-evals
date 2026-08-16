"""CLI entry point.

    python3 -m runner.run --adapter echo
    python3 -m runner.run --adapter openai --model gpt-4.1 --suite art50-transparency
    python3 -m runner.run --adapter http --endpoint https://my-agent/chat --format md
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from . import adapters, graders, report
from .cases import Case, CaseError, load_suites

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS_DIR = os.path.join(ROOT, "evals")


def run_case(case: Case, adapter, grader_fn) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": case.id,
        "suite": case.suite,
        "obligation": case.obligation.label,
        "obligation_summary": case.obligation.summary,
        "severity": case.severity,
        "passed": False,
        "detail": "",
        "graded_by": "deterministic",
        "error": None,
    }
    try:
        if case.variants:
            responses = [adapter(case.render(v), case.system) for v in case.variants]
        else:
            responses = [adapter(case.render(), case.system)]
        verdict = graders.grade(case.grader, responses, grader_fn)
        row.update(passed=verdict.passed, detail=verdict.detail, graded_by=verdict.graded_by)
        row["responses"] = responses
    except Exception as exc:  # a broken system under test is a result, not a crash
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["detail"] = row["error"]
    return row


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="runner.run",
        description="Run governance evals against a deployed model or agent.")
    p.add_argument("--adapter", default="echo",
                   choices=["echo", "openai", "anthropic", "http", "command"],
                   help="how to reach the system under test (default: echo, offline stub)")
    p.add_argument("--model", default="", help="model id, for the openai/anthropic adapters")
    p.add_argument("--base-url", default=None, help="override the API base URL")
    p.add_argument("--endpoint", default=None, help="URL for the http adapter")
    p.add_argument("--command", default=None, help="shell command for the command adapter")
    p.add_argument("--suite", action="append", default=None,
                   help="limit to a suite directory; repeatable")
    p.add_argument("--format", default="md", choices=["md", "json"])
    p.add_argument("--out", default=None, help="write the report here instead of stdout")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--grader-adapter", default=None,
                   choices=["openai", "anthropic"],
                   help="model to use for model_graded cases; without it they fail closed")
    p.add_argument("--grader-model", default="")
    p.add_argument("--fail-on", default="high", choices=["any", "high", "never"],
                   help="exit non-zero when cases fail (default: high severity only)")
    args = p.parse_args(argv)

    try:
        cases = load_suites(EVALS_DIR, args.suite)
    except CaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not cases:
        print("error: no cases found", file=sys.stderr)
        return 2

    adapter = adapters.build(args.adapter, args.model, args.base_url, args.endpoint, args.command)
    grader_fn = None
    if args.grader_adapter:
        grader_fn = adapters.build(args.grader_adapter, args.grader_model or args.model,
                                   args.base_url, None, None)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        results = list(pool.map(lambda c: run_case(c, adapter, grader_fn), cases))

    meta = {"adapter": args.adapter, "model": args.model, "suites": sorted({c.suite for c in cases}),
            "case_count": len(cases)}
    text = report.to_markdown(results, meta) if args.format == "md" else report.to_json(results, meta)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.out}")
    else:
        print(text)

    failed = [r for r in results if not r["passed"]]
    high = [r for r in failed if r["severity"] == "high"]
    if args.fail_on == "any" and failed:
        return 1
    if args.fail_on == "high" and high:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
