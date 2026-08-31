"""Builds results/RESULTS.md from whatever score files exist.

Rows appear only if their score file is present, so a partial run produces a
partial table rather than a table with invented numbers in it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROWS = [
    ("score_baseline_a.json",       "A. One direct prompt",
     "Whole statement in context, one call, JSON out"),
    ("score_baseline_b.json",       "B. Script matcher (no LLM)",
     "Fuzzy name + amount, greedy 1:1"),
    ("score_settle_core.json",      "Settle: tools only, no model",
     "Retrieval + solver + gate, escalate all ambiguity"),
    ("score_settle_fullctx.json",   "Settle: full statement in context",
     "Removed experiment: shortlist replaced by whole statement"),
    ("score_settle_noverify.json",  "Settle: adjudicator, no verifier",
     "Model decides identity, nothing checks it"),
    ("score_settle_nomem.json",     "Settle: adjudicator + verifier, cold",
     "No alias memory"),
    ("score_settle_full.json",      "Settle: full",
     "Adjudicator + verifier + gate + memory"),
    ("score_settle_ceiling.json",   "Ceiling: perfect identity judge",
     "Not a solution -- measures headroom in the tool layer"),
]


def _fmt(v, pct=False, money=False):
    if v is None:
        return "--"
    if money:
        return f"{int(v):,}"
    if pct:
        return f"{v * 100:.1f}%"
    return f"{v}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=Path("results"))
    ap.add_argument("--out", type=Path, default=Path("results/RESULTS.md"))
    args = ap.parse_args()

    lines = [
        "# Results",
        "",
        "12 seeded synthetic cases, generated with `--seed 42`. Ground truth is",
        "exact; no LLM judge is used anywhere in scoring. Primary metric is",
        "**value-weighted reconciliation F1** over (invoice, receipt) pairs,",
        "weighted by the gross amount of each transaction.",
        "",
        "| System | Cases | Value F1 | Precision | Recall | Invoices exact | Misposted KES | Escalations /100 | Escalation precision | Ledger OK | $/case |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    present = []
    for fname, label, _note in ROWS:
        p = args.results / fname
        if not p.exists():
            continue
        agg = json.loads(p.read_text(encoding="utf-8")).get("aggregate", {})
        if not agg:
            continue
        present.append((label, agg))
        lines.append(
            f"| {label} | {agg.get('cases', '?')} | **{_fmt(agg.get('value_f1'))}** | "
            f"{_fmt(agg.get('value_precision'))} | {_fmt(agg.get('value_recall'))} | "
            f"{_fmt(agg.get('invoice_exact_rate'), pct=True)} | "
            f"{_fmt(agg.get('misposted_value'), money=True)} | "
            f"{_fmt(agg.get('human_touch_per_100'))} | "
            f"{_fmt(agg.get('escalation_precision'))} | "
            f"{_fmt(agg.get('ledger_ok_rate'), pct=True)} | "
            f"{_fmt(agg.get('cost_usd_per_case'))} |")

    max_cases = max((a.get("cases", 0) for _, a in present), default=0)
    partial = [(lbl, a["cases"]) for lbl, a in present
               if a.get("cases", 0) < max_cases]
    if partial:
        lines += ["",
                  "> **Incomplete rows.** These systems were scored on fewer "
                  "cases than the rest, so their",
                  "> numbers are not comparable to the full-corpus rows above:"]
        for lbl, n in partial:
            lines.append(f"> {lbl} -- {n} of {max_cases} cases.")
        lines.append("")

    lines += ["", "### What each row is", ""]
    for fname, label, note in ROWS:
        if (args.results / fname).exists():
            lines.append(f"- **{label}** -- {note}")

    lines += [
        "",
        "### Reading the table",
        "",
        "`Misposted KES` is the value of transactions attached to the wrong",
        "invoice. In this domain it is the error that matters most: an unmatched",
        "invoice gets chased, a falsely matched one is silently written off.",
        "",
        "`Escalation precision` is the fraction of queued exceptions where the",
        "system's own unassisted best guess would have been wrong. A system that",
        "escalates everything scores well on mispostings and badly here.",
        "",
        "Per-case detail is in the `score_*.json` files beside this one.",
    ]

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[6:6 + 2 + len(present)]))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
