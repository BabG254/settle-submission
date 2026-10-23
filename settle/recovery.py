"""Rebuild alias-learning hints from previously validated approval records.

Recovery is conservative: approvals must still pass the ledger gate. Conflicting
existing aliases are reported, never overwritten.
"""
from __future__ import annotations
import json
from pathlib import Path
from .memory import AliasMemory
from .schema import read_case
from .tools import check_ledger
from .locking import file_lock


def recover_approvals(pred_path: Path, data_root: Path, db_path: Path) -> dict:
    with file_lock(pred_path.with_name(pred_path.name + ".lock")):
        pred = json.loads(pred_path.read_text(encoding="utf-8"))
        case = read_case(data_root / pred["case_id"])
        report = check_ledger(pred.get("matching", {}), case.invoices, case.txns)
        if not report.ok:
            raise ValueError("cannot recover from invalid ledger: " + report.summary())
        by_i = {i.invoice_id: i for i in case.invoices}
        by_r = {t.receipt: t for t in case.txns}
        memory = AliasMemory(db_path)
        recovered, conflicts = 0, []
        try:
            for approval in pred.get("human_approvals", []):
                inv_id = approval["invoice_id"]
                receipts = approval["receipts"]
                if pred["matching"].get(inv_id) != receipts or inv_id not in by_i:
                    conflicts.append(inv_id + ": approval differs from durable match")
                    continue
                inv = by_i[inv_id]
                for receipt in receipts:
                    if receipt not in by_r:
                        conflicts.append(inv_id + ": unknown receipt")
                        continue
                    payer = by_r[receipt].party_name
                    previous = memory.lookup(payer)
                    if previous is not None and previous != inv.customer_id:
                        conflicts.append(inv_id + ": alias conflict; manual review required")
                        continue
                    if memory.remember(payer, inv.customer_id, inv.customer_name,
                                       "human_approval", "recovered approved " + inv_id):
                        recovered += 1
        finally:
            memory.conn.close()
        return {"aliases_recovered": recovered, "conflicts": conflicts}
