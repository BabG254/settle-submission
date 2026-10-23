"""Pure approval validation and atomic persistence primitives."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .schema import Case
from .tools import check_ledger


class ApprovalError(ValueError):
    """Rejected approval that must not modify stored state."""


def validate_approval(pred: dict, case: Case, invoice_id: str,
                      receipts: list[str]) -> dict:
    """Prepare a valid approval without mutating the input or disk."""
    exceptions = pred.get("exceptions", [])
    if invoice_id in pred.get("matching", {}):
        raise ApprovalError("invoice is already matched")
    if not any(e.get("invoice_id") == invoice_id for e in exceptions):
        raise ApprovalError("invoice is not in the outstanding exception queue")
    if not receipts or len(receipts) != len(set(receipts)):
        raise ApprovalError("approval requires unique nonempty receipt IDs")
    valid_receipts = {t.receipt for t in case.txns}
    if not set(receipts) <= valid_receipts:
        raise ApprovalError("approval contains a receipt absent from the statement")
    proposal = dict(pred)
    proposal["matching"] = dict(pred.get("matching", {}))
    proposal["matching"][invoice_id] = list(receipts)
    report = check_ledger(proposal["matching"], case.invoices, case.txns)
    if not report.ok:
        raise ApprovalError("approval rejected by ledger gate: " + report.summary())
    proposal["exceptions"] = [e for e in exceptions if e.get("invoice_id") != invoice_id]
    approvals = list(pred.get("human_approvals", []))
    approvals.append({"invoice_id": invoice_id, "receipts": list(receipts)})
    proposal["human_approvals"] = approvals
    return proposal


def atomic_write_json(path: Path, value: dict) -> None:
    """Durably replace the file using a same-directory temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix="." + path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temp = Path(handle.name)
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()

def locked_prediction(path: Path):
    """Portable exclusive lock for a prediction's full read-modify-write cycle."""
    from .locking import file_lock
    return file_lock(path.with_name(path.name + ".lock"))
