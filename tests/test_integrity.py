"""Regression tests for post-ledger alias learning and receipt integrity."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from settle.agent import Settle
from settle.memory import AliasMemory
from settle.schema import Invoice, Txn
from settle.tools import check_ledger


def inv(identifier: str = "INV-1", amount: int = 100) -> Invoice:
    return Invoice(identifier, "C-1", "Grace Njeri", amount, "2026-01-01", "2026-01-10")


def tx(identifier: str = "R-1", amount: int = 100, kind: str = "pay_bill") -> Txn:
    return Txn(identifier, "2026-01-02T09:00:00", kind, "Grace Njeri",
               "2547*****001", amount, 0, 0, "")


class AliasSafetyTests(unittest.TestCase):
    def test_only_surviving_invoices_are_learned(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = AliasMemory(Path(folder) / "memory.db")
            agent = Settle(model="offline", use_adjudicator=False, memory=memory)
            pending = [
                ("INV-1", "GRACE NJERI", "C-1", "Grace Njeri", "verified"),
                ("INV-2", "OTHER PAYER", "C-2", "Other", "withdrawn"),
            ]
            agent._commit_verified_aliases(pending, {"INV-1": ["R-1"]})
            self.assertEqual(memory.lookup("GRACE NJERI"), "C-1")
            self.assertIsNone(memory.lookup("OTHER PAYER"))
            memory.conn.close()

    def test_no_learning_without_final_gate(self):
        from settle.schema import Case
        with tempfile.TemporaryDirectory() as folder:
            memory = AliasMemory(Path(folder) / "memory.db")
            agent = Settle(model="offline", use_adjudicator=False,
                           use_gate=False, memory=memory)
            case = Case("case", [inv()], [tx()], [], [])
            result = agent.run(case)
            self.assertIn("INV-1", result["matching"])
            self.assertEqual(memory.size(), 0)
            memory.conn.close()


class IntegrityTests(unittest.TestCase):
    def test_unknown_invoice_is_rejected(self):
        report = check_ledger({"NONEXISTENT": ["R-1"]}, [inv()], [tx()])
        self.assertFalse(report.ok)

    def test_duplicate_receipt_within_same_invoice_is_rejected(self):
        report = check_ledger({"INV-1": ["R-1", "R-1"]},
                              [inv(amount=200)], [tx()])
        self.assertFalse(report.ok)

    def test_non_payment_receipt_is_rejected(self):
        report = check_ledger({"INV-1": ["C-1"]}, [inv()], [tx("C-1", kind="charge")])
        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
