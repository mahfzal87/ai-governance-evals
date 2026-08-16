"""Load and validate eval case files."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .graders import KNOWN_GRADERS, PATTERN_KEYS

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required to read the eval cases.\n"
        "  pip install -r requirements.txt\n"
        "It is the only dependency; everything else is standard library."
    )

REQUIRED = ("id", "obligation", "prompt", "grader")
VALID_SEVERITY = ("high", "medium", "low")


@dataclass
class Obligation:
    instrument: str
    reference: str
    summary: str

    @property
    def label(self) -> str:
        return f"{self.instrument} {self.reference}"


@dataclass
class Case:
    id: str
    suite: str
    obligation: Obligation
    prompt: str
    grader: Dict[str, Any]
    severity: str = "medium"
    system: Optional[str] = None
    rationale: str = ""
    # Some graders (consistency) run the prompt several times with substitutions.
    variants: List[Dict[str, str]] = field(default_factory=list)
    path: str = ""

    def render(self, variant: Optional[Dict[str, str]] = None) -> str:
        text = self.prompt
        for key, value in (variant or {}).items():
            text = text.replace("{{" + key + "}}", value)
        return text


class CaseError(ValueError):
    pass


def _validate(raw: Dict[str, Any], path: str) -> None:
    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        raise CaseError(f"{path}: missing required key(s): {', '.join(missing)}")

    ob = raw["obligation"]
    if not isinstance(ob, dict):
        raise CaseError(f"{path}: 'obligation' must be a mapping")
    for k in ("instrument", "reference", "summary"):
        if k not in ob:
            raise CaseError(f"{path}: obligation is missing '{k}'")

    grader = raw["grader"]
    if not isinstance(grader, dict) or "type" not in grader:
        raise CaseError(f"{path}: 'grader' must be a mapping with a 'type'")
    kind = grader["type"]
    if kind not in KNOWN_GRADERS:
        raise CaseError(f"{path}: unknown grader type {kind!r}; "
                        f"expected one of {sorted(KNOWN_GRADERS)}")
    for required_key in KNOWN_GRADERS[kind]:
        if not grader.get(required_key):
            raise CaseError(f"{path}: grader {kind!r} requires a non-empty {required_key!r}")
    for key in PATTERN_KEYS:
        for pat in grader.get(key) or []:
            try:
                re.compile(pat)
            except re.error as exc:
                raise CaseError(f"{path}: bad regex in {key}: {pat!r} ({exc})")

    sev = raw.get("severity", "medium")
    if sev not in VALID_SEVERITY:
        raise CaseError(f"{path}: severity must be one of {VALID_SEVERITY}, got {sev!r}")

    if grader["type"] == "consistency" and not raw.get("variants"):
        raise CaseError(f"{path}: the 'consistency' grader requires 'variants'")


def load_case(path: str, suite: str) -> Case:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise CaseError(f"{path}: file must contain a single YAML mapping")
    _validate(raw, path)
    ob = raw["obligation"]
    return Case(
        id=raw["id"],
        suite=suite,
        obligation=Obligation(ob["instrument"].strip(), str(ob["reference"]).strip(),
                              " ".join(ob["summary"].split())),
        prompt=raw["prompt"],
        grader=raw["grader"],
        severity=raw.get("severity", "medium"),
        system=raw.get("system"),
        rationale=(raw.get("rationale") or "").strip(),
        variants=raw.get("variants") or [],
        path=path,
    )


def load_suites(root: str, only: Optional[List[str]] = None) -> List[Case]:
    cases: List[Case] = []
    seen_ids = set()
    for suite in sorted(os.listdir(root)):
        suite_dir = os.path.join(root, suite)
        if not os.path.isdir(suite_dir):
            continue
        if only and suite not in only:
            continue
        for name in sorted(os.listdir(suite_dir)):
            if not name.endswith((".yaml", ".yml")):
                continue
            case = load_case(os.path.join(suite_dir, name), suite)
            if case.id in seen_ids:
                raise CaseError(f"duplicate case id: {case.id}")
            seen_ids.add(case.id)
            cases.append(case)
    if only:
        missing = set(only) - {c.suite for c in cases}
        if missing:
            raise CaseError(f"no such suite(s): {', '.join(sorted(missing))}")
    return cases
