"""Render captured trajectories to readable markdown.

Judges asked for representative trajectories they can follow from instructions
to result. The JSONL is the record; this makes it readable.

    python -m settle.trajectory --in trajectories/full --out trajectories/rendered
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(path: Path) -> str:
    out = [f"# Trajectory: {path.stem}", ""]
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        kind = rec.get("type")

        if kind == "retrieval":
            out += [f"### Retrieval -- {rec['invoice']}",
                    "",
                    f"- statement rows available: **{rec['statement_rows']}**",
                    f"- shortlisted for this invoice: **{rec['shortlisted']}**",
                    f"- combinations summing exactly to the invoice: "
                    f"**{rec['exact_combinations']}**", ""]
        elif kind == "auto_accept":
            out += [f"**Deterministic accept** -- {rec['invoice']} -> "
                    f"`{', '.join(rec['receipts'])}` ({rec['why']}). No model call.",
                    ""]
        elif kind == "model_call":
            u = rec.get("usage", {})
            out += [f"### Model call ({rec['role']})",
                    "",
                    f"`{rec['model']}` -- {rec['elapsed_s']}s, "
                    f"{u.get('input_tokens')} in / {u.get('output_tokens')} out",
                    "",
                    "<details><summary>System instructions</summary>", "",
                    "```", rec.get("system", "")[:4000], "```", "", "</details>", "",
                    "<details><summary>Input</summary>", "",
                    "```", rec.get("user", "")[:6000], "```", "", "</details>", "",
                    "**Output**", "",
                    "```json", rec.get("output", "")[:3000], "```", ""]
        elif kind == "verifier_reject":
            out += [f"> **Verifier rejected** {rec['invoice']}: "
                    f"{rec.get('objection')}", "",
                    "> Escalated to the exception queue instead of posted.", ""]
        elif kind == "gate_reject":
            out += [f"> **Gate rejected** {rec['invoice']}: {rec.get('why')}", ""]
        elif kind == "memory_write":
            out += [f"> **Alias learned**: `{rec['alias']}` -> {rec['customer']} "
                    f"(from {rec['invoice']})", ""]
        elif kind == "ledger_gate":
            out += ["---", "", f"### Ledger gate -- {rec['case']}", "",
                    "```", rec.get("summary", ""), "```", ""]
            if rec.get("withdrawn"):
                out += [f"Withdrawn to exceptions by the gate: "
                        f"{', '.join(rec['withdrawn'])}", ""]
        else:
            out += [f"- `{kind}` {json.dumps({k: v for k, v in rec.items() if k not in {'ts', 'type'}})[:300]}", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", type=Path, required=True)
    ap.add_argument("--out", dest="dst", type=Path, required=True)
    args = ap.parse_args()
    args.dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(args.src.glob("*.jsonl")):
        (args.dst / f"{f.stem}.md").write_text(render(f), encoding="utf-8")
        n += 1
    print(f"rendered {n} trajectories to {args.dst}")


if __name__ == "__main__":
    main()
