"""Report rendering. Grouped by obligation, because that is the unit people act on."""
from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, Dict, List

BANNER = (
    "> [!IMPORTANT]\n"
    "> This report records observed behaviour on a sample of probes. It is not a\n"
    "> compliance assessment, an audit, or evidence of conformity. Passing every\n"
    "> case means the system handled these specific inputs as expected, nothing\n"
    "> more. Most obligations in the instruments referenced here are documentation\n"
    "> and process duties that no behavioural test can observe.\n"
)


def to_json(results: List[Dict[str, Any]], meta: Dict[str, Any]) -> str:
    return json.dumps({"meta": meta, "results": results}, indent=2)


def to_markdown(results: List[Dict[str, Any]], meta: Dict[str, Any]) -> str:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    errors = sum(1 for r in results if r.get("error"))
    failed = total - passed - errors

    high_fail = [r for r in results if not r["passed"] and r["severity"] == "high" and not r.get("error")]

    out = ["# Governance eval report", ""]
    out.append(f"**System under test:** `{meta['adapter']}`"
               + (f" / `{meta['model']}`" if meta.get("model") else ""))
    out.append("")
    out.append(f"**Result:** {passed}/{total} passed"
               + (f", {failed} failed" if failed else "")
               + (f", {errors} errored" if errors else ""))
    out.append("")
    if high_fail:
        out.append(f"**{len(high_fail)} high-severity failure(s).** "
                   "These are the ones to look at first.")
        out.append("")
    high_err = [r for r in results if r.get("error") and r["severity"] == "high"]
    if high_err:
        out.append(f"**{len(high_err)} high-severity case(s) errored.** "
                   "These count as failures for the exit code.")
        out.append("")
    out.append(BANNER)
    out.append("")

    by_ob: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for r in results:
        by_ob.setdefault(r["obligation"], []).append(r)

    out.append("## Results by obligation")
    out.append("")
    for ob, rows in by_ob.items():
        ok = sum(1 for r in rows if r["passed"])
        out.append(f"### {ob} &nbsp; ({ok}/{len(rows)})")
        out.append("")
        out.append(f"_{rows[0]['obligation_summary']}_")
        out.append("")
        out.append("| Case | Severity | Result | Graded by | Detail |")
        out.append("|---|---|---|---|---|")
        for r in rows:
            if r.get("error"):
                mark = "ERROR"
            else:
                mark = "pass" if r["passed"] else "**FAIL**"
            detail = str(r.get("detail", "")).replace("|", "\\|")[:160]
            out.append(f"| `{r['id']}` | {r['severity']} | {mark} | {r.get('graded_by','-')} | {detail} |")
        out.append("")

    out.append("## What this does not cover")
    out.append("")
    out.append(
        "Behavioural probes can observe what a system says and does. They cannot observe "
        "whether technical documentation exists, whether a risk management system is "
        "operating, whether logs are retained for the required period, whether a "
        "conformity assessment was carried out, or whether the system is registered. "
        "Those are the majority of the obligations, and they are checked against records, "
        "not prompts."
    )
    out.append("")
    return "\n".join(out)
