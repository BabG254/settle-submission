"""Small read-only helpers, so the video demo does not need inline one-liners.

    python -m settle.show reversals --pred results/pred_baseline_b/case09.json
    python -m settle.show queue     --pred results/pred_demo/month01.json --data data/memory_demo
    python -m settle.show table
    python -m settle.show statement --case data/case12 --rows 25
    python -m settle.show aliases   --db state/demo.db
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .schema import read_case


def cmd_reversals(args) -> None:
    pred = json.loads(args.pred.read_text(encoding="utf-8"))
    errs = pred.get("ledger_errors") or []
    if not errs:
        ok = pred.get("ledger_ok")
        print(f"{pred['case_id']}: ledger_ok={ok}, no violations recorded")
        return
    print(f"{pred['case_id']} -- ledger violations in this system's output:\n")
    for e in errs[: args.limit]:
        print(f"  {e}")
    reversed_ = [e for e in errs if "was reversed" in e]
    if reversed_:
        print(f"\n  {len(reversed_)} of these are payments that were REFUNDED "
              f"and reported as revenue.")


def cmd_queue(args) -> None:
    pred = json.loads(args.pred.read_text(encoding="utf-8"))
    case = read_case(args.data / pred["case_id"])
    by_r = {t.receipt: t for t in case.txns}
    exceptions = pred.get("exceptions", [])
    if args.invoice:
        exceptions = [e for e in exceptions if e["invoice_id"] == args.invoice]

    print(f"{pred['case_id']}: {len(pred.get('matching', {}))} matched, "
          f"{len(pred.get('exceptions', []))} queued for review\n")
    for e in exceptions[: args.limit]:
        print(f"{e['invoice_id']}  {e.get('customer', '')}  "
              f"KES {e.get('amount', 0):,}")
        print(f"  reason: {e['reason']}")
        for n, o in enumerate(e.get("options", []), 1):
            payers = sorted({by_r[r].party_name for r in o if r in by_r})
            total = sum(by_r[r].gross for r in o if r in by_r)
            print(f"  [{n}] {', '.join(o)}")
            print(f"      payer(s): {', '.join(payers)}   gross {total:,}")
        print()


def cmd_table(args) -> None:
    p = args.results / "RESULTS.md"
    if not p.exists():
        print("no results yet -- run the report target first")
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") or line.startswith("#"):
            print(line)


def cmd_statement(args) -> None:
    case = read_case(args.case)
    print(f"{case.case_id}: {len(case.invoices)} invoices, {len(case.txns)} statement rows\n")
    print(f"  {'receipt':<12} {'date':<11} {'party':<30} {'net':>9} {'fee':>5} {'kind'}")
    for t in case.txns[: args.rows]:
        print(f"  {t.receipt:<12} {t.datetime[:10]:<11} {t.party_name[:29]:<30} "
              f"{t.paid_in:>9,} {t.fee:>5,} {t.kind}")
    if len(case.txns) > args.rows:
        print(f"  ... {len(case.txns) - args.rows} more rows")


def cmd_aliases(args) -> None:
    from .memory import AliasMemory
    mem = AliasMemory(args.db)
    rows = mem.dump()
    if not rows:
        print(f"{args.db}: empty -- nothing approved yet")
        return
    print(f"{args.db}: {len(rows)} approved identities\n")
    for r in rows:
        print(f"  {r['party_raw']:<28} -> {r['customer_name']} ({r['customer_id']})")
        print(f"     via {r['source']}, {r['first_seen'][:10]} -- {r['evidence'][:70]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Read-only demo helpers.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("reversals", help="show ledger violations in a prediction file")
    p.add_argument("--pred", type=Path, required=True)
    p.add_argument("--limit", type=int, default=6)
    p.set_defaults(fn=cmd_reversals)

    p = sub.add_parser("queue", help="show the exception queue with its options")
    p.add_argument("--pred", type=Path, required=True)
    p.add_argument("--data", type=Path, default=Path("data"))
    p.add_argument("--invoice", default=None)
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(fn=cmd_queue)

    p = sub.add_parser("table", help="print the results table")
    p.add_argument("--results", type=Path, default=Path("results"))
    p.set_defaults(fn=cmd_table)

    p = sub.add_parser("statement", help="print a statement head")
    p.add_argument("--case", type=Path, default=Path("data/case12"))
    p.add_argument("--rows", type=int, default=25)
    p.set_defaults(fn=cmd_statement)

    p = sub.add_parser("aliases", help="print the alias memory contents")
    p.add_argument("--db", type=Path, default=Path("state/aliases.db"))
    p.set_defaults(fn=cmd_aliases)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
