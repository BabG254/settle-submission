"""Human checkpoint.

An exception is not a dead end. This is the tool the bookkeeper uses to clear
one, and it is the only place in the system where a person's judgement is
recorded. Clearing an exception does two things: it posts the match, and it
teaches the alias store who that payer is, so the same spelling never has to be
escalated again.

    python -m settle.approve --pred results/pred_demo/month01.json \\
        --data data/memory_demo --invoice month01-INV003 --option 1
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .memory import AliasMemory
from .schema import read_case
from .tools import check_ledger


def main() -> None:
    ap = argparse.ArgumentParser(description="Approve or reject a queued exception.")
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--invoice", required=True)
    ap.add_argument("--option", type=int, default=None,
                    help="1-based index into the queued options")
    ap.add_argument("--receipts", default=None, help="comma-separated, overrides --option")
    ap.add_argument("--reject", action="store_true", help="mark as genuinely unpaid")
    ap.add_argument("--memory-db", type=Path, default=Path("state/aliases.db"))
    ap.add_argument("--list", action="store_true", help="just show the queue")
    args = ap.parse_args()

    pred = json.loads(args.pred.read_text(encoding="utf-8"))
    case = read_case(args.data / pred["case_id"])
    by_r = {t.receipt: t for t in case.txns}
    by_i = {i.invoice_id: i for i in case.invoices}

    if args.list:
        for e in pred["exceptions"]:
            print(f"\n{e['invoice_id']}  {e.get('customer','')}  "
                  f"KES {e.get('amount',0):,}\n  reason: {e['reason']}")
            for n, o in enumerate(e.get("options", []), 1):
                payers = sorted({by_r[r].party_name for r in o if r in by_r})
                total = sum(by_r[r].gross for r in o if r in by_r)
                print(f"  [{n}] {', '.join(o)}  payer(s): {', '.join(payers)}  "
                      f"gross {total:,}")
        return

    exc = next((e for e in pred["exceptions"] if e["invoice_id"] == args.invoice), None)
    if exc is None:
        raise SystemExit(f"{args.invoice} is not in the exception queue")

    if args.reject:
        exc["resolution"] = "rejected: invoice genuinely unpaid"
        args.pred.write_text(json.dumps(pred, indent=2), encoding="utf-8")
        print(f"{args.invoice}: marked unpaid, no alias written")
        return

    if args.receipts:
        receipts = [r.strip() for r in args.receipts.split(",") if r.strip()]
    elif args.option:
        receipts = exc["options"][args.option - 1]
    else:
        raise SystemExit("give --option or --receipts (or --list to see the queue)")

    inv = by_i[args.invoice]
    trial = dict(pred["matching"])
    trial[args.invoice] = receipts
    report = check_ledger(trial, case.invoices, case.txns)
    if not report.ok:
        # The gate applies to humans too. An approval that unbalances the ledger
        # is refused, not accepted with a warning.
        raise SystemExit("approval refused by the ledger gate:\n" + report.summary())

    memory = AliasMemory(args.memory_db)
    payers = sorted({by_r[r].party_name for r in receipts})
    written = []
    for p in payers:
        if memory.remember(p, inv.customer_id, inv.customer_name,
                           source="human_approval",
                           evidence=f"approved on {inv.invoice_id} "
                                    f"(KES {inv.amount:,})"):
            written.append(p)

    pred["matching"] = trial
    pred["exceptions"] = [e for e in pred["exceptions"]
                          if e["invoice_id"] != args.invoice]
    pred.setdefault("human_approvals", []).append(
        {"invoice_id": args.invoice, "receipts": receipts, "aliases_learned": written})
    args.pred.write_text(json.dumps(pred, indent=2), encoding="utf-8")

    print(f"{args.invoice}: posted {', '.join(receipts)}")
    print(f"  ledger: {report.summary()}")
    for p in written:
        print(f"  learned: {p!r} -> {inv.customer_name} ({inv.customer_id})")
    print(f"  alias store now holds {memory.size()} approved identities")


if __name__ == "__main__":
    main()
