"""The two baselines.

Baseline B exists to answer the question a judge should ask first: could you
have just written a script? It is not a straw man. It gets the fee gross-up
right, it uses the same fuzzy matcher, and on clean one-to-one cases it is very
hard to beat. What it cannot do is search combinations, pair reversals, or
decide that MAMA NJERI GROCERS is Njeri Wambui Enterprises.

Baseline A is the obvious agentic approach: put the statement in the context
window and ask for the matching in one shot.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .schema import Invoice, Txn, read_case
from .tools import check_ledger, name_score

NAME_FLOOR = 62.0   # below this a script would not claim a match


# ------------------------------------------------------- B: script matcher

def baseline_b(invoices: list[Invoice], txns: list[Txn]) -> dict:
    """Greedy 1:1 matcher: amount (net or grossed-up) + fuzzy name + date order."""
    used: set[str] = set()
    matching: dict[str, list[str]] = {}

    scored: list[tuple[float, str, str]] = []
    for inv in invoices:
        for t in txns:
            if t.kind != "pay_bill":
                continue
            if t.paid_in != inv.amount and t.gross != inv.amount:
                continue
            ns = name_score(inv.customer_name, t.party_name)
            if ns < NAME_FLOOR:
                continue
            scored.append((ns, inv.invoice_id, t.receipt))

    # highest-confidence pairs claim their transaction first
    scored.sort(key=lambda x: -x[0])
    claimed_inv: set[str] = set()
    for ns, inv_id, receipt in scored:
        if inv_id in claimed_inv or receipt in used:
            continue
        claimed_inv.add(inv_id)
        used.add(receipt)
        matching[inv_id] = [receipt]

    # A script has no notion of "I am unsure", so it queues nothing. We still
    # run the ledger check over its output, to report whether the numbers it
    # produced would survive verification -- it is not gated by it.
    report = check_ledger(matching, invoices, txns)
    return {
        "system": "baseline_b_script",
        "matching": matching,
        "exceptions": [],
        "ledger_ok": report.ok,
        "ledger_errors": report.errors[:20],
        "meta": {"cost_usd": 0.0},
    }


# ---------------------------------------------------- A: one direct prompt

BASELINE_A_PROMPT = """You are reconciling a small business's accounts.

Below are the open invoices and the full mobile-money statement for the period.
Match each invoice to the transaction or transactions that paid it.

INVOICES (CSV):
{invoices}

MOBILE MONEY STATEMENT (CSV):
{statement}

Return ONLY a JSON object, no prose and no markdown fences, of the form:
{{"matching": {{"<invoice_id>": ["<receipt>", ...], ...}}}}
Omit an invoice entirely if you believe it was not paid.
"""


def _csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    cols = list(rows[0].keys())
    lines = [",".join(cols)]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")) for c in cols))
    return "\n".join(lines)


def baseline_a(invoices: list[Invoice], txns: list[Txn], model: str) -> dict:
    from .llm import call_model, check_request_size, price

    inv_rows = [{"invoice_id": i.invoice_id, "customer_name": i.customer_name,
                 "amount": i.amount, "issue_date": i.issue_date} for i in invoices]
    txn_rows = [{"receipt": t.receipt, "datetime": t.datetime, "kind": t.kind,
                 "party_name": t.party_name, "party_phone": t.party_phone,
                 "paid_in": t.paid_in, "fee": t.fee, "withdrawn": t.withdrawn,
                 "narration": t.narration} for t in txns]

    prompt = BASELINE_A_PROMPT.format(invoices=_csv(inv_rows), statement=_csv(txn_rows))
    too_big = check_request_size("", prompt, 8000)
    if too_big:
        # Baseline A's whole design is "put the statement in the context
        # window", so on a small per-minute budget the larger cases simply
        # cannot run. That is a real finding about the baseline, not a bug --
        # but it must be recorded, not silently scored as a miss.
        raise RuntimeError(f"baseline A does not fit this tier: {too_big}")
    t0 = time.time()
    text, usage = call_model(model, system="", user=prompt, max_tokens=8000)
    elapsed = time.time() - t0

    matching: dict[str, list[str]] = {}
    try:
        cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        matching = json.loads(cleaned).get("matching", {})
    except Exception as exc:                                    # noqa: BLE001
        print(f"  ! baseline A returned unparseable output: {exc}")

    report = check_ledger(matching, invoices, txns)
    return {
        "system": "baseline_a_prompt",
        "matching": matching,
        "exceptions": [],
        "ledger_ok": report.ok,
        "ledger_errors": report.errors[:20],
        "meta": {"cost_usd": price(model, usage), "wall_s": round(elapsed, 1),
                 "model": model, "usage": usage},
    }


# ------------------------------------------------------------------- runner

def main() -> None:
    from .llm import _load_dotenv
    _load_dotenv()
    ap = argparse.ArgumentParser(description="Run a baseline over the corpus.")
    ap.add_argument("--which", choices=["a", "b"], required=True)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default=os.environ.get("SETTLE_MODEL", "claude-sonnet-4-6"))
    ap.add_argument("--cases", nargs="*", default=None)
    ap.add_argument("--resume", action="store_true",
                    help="skip cases whose prediction file already exists")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    dirs = sorted(d for d in args.data.iterdir()
                  if d.is_dir() and (d / "truth.json").exists())
    if args.cases:
        dirs = [d for d in dirs if d.name in args.cases]

    failures = []
    for d in dirs:
        out_file = args.out / f"{d.name}.json"
        if args.resume and out_file.exists():
            print(f"  {d.name}: already done, skipping (--resume)")
            continue
        case = read_case(d)
        t0 = time.time()
        try:
            pred = (baseline_b(case.invoices, case.txns) if args.which == "b"
                    else baseline_a(case.invoices, case.txns, args.model))
        except Exception as exc:                                # noqa: BLE001
            failures.append((case.case_id, f"{type(exc).__name__}: {exc}"))
            print(f"  {case.case_id}: FAILED -- {type(exc).__name__}: {exc}")
            continue
        pred["case_id"] = case.case_id
        pred.setdefault("meta", {}).setdefault("wall_s", round(time.time() - t0, 2))
        out_file.write_text(json.dumps(pred, indent=2), encoding="utf-8")
        print(f"  {case.case_id}: matched {len(pred['matching'])}/{len(case.invoices)} invoices")

    if failures:
        print(f"\n  {len(failures)} case(s) failed; re-run with --resume to retry only these:")
        for cid, err in failures:
            print(f"    {cid}: {err}")


if __name__ == "__main__":
    main()
