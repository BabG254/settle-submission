"""Conservative global matching and independently checkable bank settlements."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .schema import BankLine, Invoice, Txn
from .tools import propose_candidates, subset_solver, reversal_pairs


@dataclass
class SettlementReport:
    ok: bool
    errors: list[str]
    checked: int


def verify_settlements(bank: list[BankLine], txns: list[Txn], *,
                       maximum_lag_days: int = 3) -> SettlementReport:
    """Verify explicit receipt-linked settlement batches.

    Empty links are unverified, not silently assumed valid. Bank fees and
    provider-specific adjustments require an explicitly specified policy.
    """
    errors: list[str] = []
    by_receipt = {t.receipt: t for t in txns}
    if len(by_receipt) != len(txns):
        errors.append("duplicate statement receipt identifiers")
    reversed_ids = reversal_pairs(txns)
    seen: set[str] = set()
    bank_refs: set[str] = set()
    for line in bank:
        if line.ref in bank_refs:
            errors.append(f"{line.ref}: duplicate bank reference")
        bank_refs.add(line.ref)
        if not line.settles:
            errors.append(f"{line.ref}: no receipt links; settlement unverified")
            continue
        total = 0
        for receipt in line.settles:
            if receipt in seen:
                errors.append(f"{line.ref}: receipt {receipt} allocated twice")
                continue
            seen.add(receipt)
            transaction = by_receipt.get(receipt)
            if transaction is None:
                errors.append(f"{line.ref}: receipt {receipt} missing")
                continue
            if transaction.kind != "pay_bill" or receipt in reversed_ids:
                errors.append(f"{line.ref}: receipt {receipt} is not an eligible credit")
                continue
            lag = (date.fromisoformat(line.date)
                   - datetime.fromisoformat(transaction.datetime).date()).days
            if not 0 <= lag <= maximum_lag_days:
                errors.append(f"{line.ref}: receipt {receipt} outside settlement window")
            total += transaction.paid_in
        if total != line.amount:
            errors.append(f"{line.ref}: expected {total} net, received {line.amount}")
    return SettlementReport(not errors, errors, len(bank))


def unique_global_matches(invoices: list[Invoice], txns: list[Txn], *,
                          maximum_nodes: int = 100_000) -> dict[str, list[str]]:
    """Return only assignments invariant across all feasible global solutions.

    Ambiguity is deliberately escalated rather than resolved arbitrarily.
    The bounded search fails closed if its budget is exceeded.
    """
    options = {}
    for inv in invoices:
        options[inv.invoice_id] = subset_solver(
            inv.amount, propose_candidates(inv, txns), max_results=8)
    solutions: list[dict[str, list[str]]] = []
    nodes = 0
    ordered = sorted(invoices, key=lambda inv: (len(options[inv.invoice_id]), inv.invoice_id))

    def visit(index: int, used: set[str], chosen: dict[str, list[str]]) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > maximum_nodes:
            raise OverflowError("global matching search budget exceeded")
        if index == len(ordered):
            solutions.append(dict(chosen))
            return
        inv = ordered[index]
        choices = options[inv.invoice_id]
        # An invoice without a feasible option remains unresolved.
        if not choices:
            visit(index + 1, used, chosen)
            return
        for receipts in choices:
            if used.isdisjoint(receipts):
                chosen[inv.invoice_id] = receipts
                visit(index + 1, used | set(receipts), chosen)
                del chosen[inv.invoice_id]
        # Some invoices must be left unresolved when all global choices conflict.
        visit(index + 1, used, chosen)

    try:
        visit(0, set(), {})
    except OverflowError:
        return {}
    if not solutions:
        return {}
    # Prefer assignments maximizing the number of resolved invoices. Do not
    # break ties by arbitrary ordering: keep only universally shared matches.
    best = max(map(len, solutions))
    optimal = [s for s in solutions if len(s) == best]
    first = optimal[0]
    return {invoice: receipts for invoice, receipts in first.items()
            if all(candidate.get(invoice) == receipts for candidate in optimal)}
