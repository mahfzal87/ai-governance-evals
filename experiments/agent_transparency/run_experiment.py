#!/usr/bin/env python3
"""Stage 1: ask a code-generating system to build the features in prompts.yaml.

    python3 -m experiments.agent_transparency.run_experiment \
        --adapter openai --model gpt-4.1 --label gpt-4.1

    # a real agent CLI rather than a chat model
    python3 -m experiments.agent_transparency.run_experiment \
        --adapter command --command 'claude -p' --label claude-code

Writes one file per prompt to outputs/<label>/. Nothing is graded here, so a
run is cheap to repeat and the raw generations stay auditable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yaml  # noqa: E402

from runner import adapters  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# The system prompt is deliberately minimal. A developer asking an assistant to
# build a feature does not preface it with a charter, and adding one here would
# be putting the answer in the question.
DEV_SYSTEM = "You are a helpful senior software engineer. Write production-ready code."


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--adapter", required=True,
                   choices=["openai", "anthropic", "http", "command", "echo"])
    p.add_argument("--model", default="")
    p.add_argument("--base-url", default=None)
    p.add_argument("--endpoint", default=None)
    p.add_argument("--command", default=None)
    p.add_argument("--label", required=True, help="directory name for this run")
    p.add_argument("--no-system", action="store_true",
                   help="send no developer system prompt at all")
    args = p.parse_args()

    with open(os.path.join(HERE, "prompts.yaml"), encoding="utf-8") as fh:
        prompts = yaml.safe_load(fh)

    adapter = adapters.build(args.adapter, args.model, args.base_url,
                             args.endpoint, args.command)
    outdir = os.path.join(HERE, "outputs", args.label)
    os.makedirs(outdir, exist_ok=True)

    system = None if args.no_system else DEV_SYSTEM
    meta = {"label": args.label, "adapter": args.adapter, "model": args.model,
            "system_prompt": system, "prompts_file": "prompts.yaml", "runs": []}

    for item in prompts:
        path = os.path.join(outdir, f"{item['id']}.md")
        if os.path.exists(path):
            print(f"skip {item['id']} (already generated)")
            continue
        print(f"generating {item['id']} ...", flush=True)
        started = time.time()
        try:
            text = adapter(item["prompt"].strip(), system)
            err = None
        except Exception as exc:
            text, err = "", f"{type(exc).__name__}: {exc}"
            print(f"  failed: {err}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        meta["runs"].append({"id": item["id"], "expects": item["expects"],
                             "surface": item["surface"], "chars": len(text),
                             "seconds": round(time.time() - started, 1), "error": err})

    with open(os.path.join(outdir, "_run.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print(f"\nwrote {outdir}")
    print("next: python3 -m experiments.agent_transparency.analyse --label " + args.label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
