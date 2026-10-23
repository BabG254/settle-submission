"""Executable regression tests for exact matching and ledger invariants."""
from __future__ import annotations

import unittest

from settle.schema import Invoice, Txn
from settle.tools import (
    Candidate,
    check_ledger,
    propose_candidates,
    reversal_pairs,
    subset_solver,
)


def invoice(amount: int = 1000) -> Invoice:
    return Invoice("INV-1", "C-1", "Grace Njeri", amount, "2026-01-10", "2026-01-31")


def txn(receipt: str, net: int, fee: int = 0, *, kind: str = "pay_bill",
        reverses: str | None = None, party: str = "Grace Njeri") -> Txn:
    return Txn(receipt, "2026-01-11T12:00:00", kind, party, "2547*****001",
               net, fee, 0, "", reverses)


def candidate(receipt: str, gross: int) -> Candidate:
    return Candidate(receipt, "2026-01-11T12:00:00", "Grace Njeri",
                     "2547*****001", gross, 0, gross, 100.0, None, 1)


class MatchingTests(unittest.TestCase):
    def test_exact_single_and_split_payments(self):
        candidates = [candidate("A", 400), candidate("B", 600),
                      candidate("C", 1000)]
        self.assertEqual(
            subset_solver(1000, candidates),
            [["C"], ["A", "B"]],
        )

    def test_no_match_if_total_does_not_exist(self):
        self.assertEqual(subset_solver(1000, [candidate("A", 300)]), [])

    def test_subset_part_limit(self):
        candidates = [candidate(str(i), 100) for i in range(6)]
        self.assertEqual(subset_solver(600, candidates, max_parts=5), [])

    def test_shortlist_respects_time_window_and_amount(self):
        inv = invoice()
        candidates = propose_candidates(inv, [
            txn("A", 1000),
            txn("B", 1200),
            Txn("OLD", "2025-12-01T12:00:00", "pay_bill",
                "Grace Njeri", "", 1000, 0, 0, ""),
        ])
        self.assertEqual([c.receipt for c in candidates], ["A"])

    def test_reversed_receipts_are_excluded(self):
        txns = [txn("A", 1000),
                txn("R", 0, kind="reversal", reverses="A")]
        self.assertEqual(reversal_pairs(txns), {"A", "R"})
        self.assertEqual(propose_candidates(invoice(), txns), [])
        self.assertFalse(check_ledger({"INV-1": ["A"]}, [invoice()], txns).ok)

    def test_balanced_ledger(self):
        self.assertTrue(check_ledger(
            {"INV-1": ["A", "B"]},
            [invoice()],
            [txn("A", 400), txn("B", 600)],
        ).ok)

    def test_ledger_rejects_unknown_receipts(self):
        result = check_ledger({"INV-1": ["MISSING"]}, [invoice()], [])
        self.assertFalse(result.ok)
        self.assertTrue(any("not in the statement" in e for e in result.errors))

    def test_ledger_rejects_wrong_amount(self):
        result = check_ledger({"INV-1": ["A"]}, [invoice()], [txn("A", 990)])
        self.assertFalse(result.ok)

    def test_ledger_rejects_receipt_reuse(self):
        inv2 = Invoice("INV-2", "C-2", "Other", 1000, "2026-01-10", "2026-01-31")
        result = check_ledger(
            {"INV-1": ["A"], "INV-2": ["A"]},
            [invoice(), inv2],
            [txn("A", 1000)],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("already used" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main()
