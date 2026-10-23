"""Integration tests for conservative global agent execution and bank reporting."""
import unittest
from settle.agent import Settle
from settle.schema import Case, Invoice, Txn, BankLine

def invoice(identifier, amount):
    return Invoice(identifier, identifier, "Grace Njeri", amount, "2026-01-01", "2026-01-10")

def txn(ref, amount):
    return Txn(ref, "2026-01-02T10:00:00", "pay_bill", "Grace Njeri",
               "2547*****111", amount, 0, 0, "")

class AgentIntegrationTests(unittest.TestCase):
    def test_globally_unique_match_with_valid_bank(self):
        case = Case("case", [invoice("A", 100)], [txn("R", 100)],
                    [BankLine("B", "2026-01-03", "", 100, ["R"])], [])
        result = Settle(model="offline", use_adjudicator=False,
                        global_matching=True, memory=None).run(case)
        self.assertEqual(result["matching"], {"A": ["R"]})
        self.assertTrue(result["ledger_ok"])
        self.assertTrue(result["bank_settlement_ok"])

    def test_global_ambiguity_is_escalated(self):
        case = Case("case", [invoice("A", 100), invoice("B", 100)],
                    [txn("R", 100)], [], [])
        result = Settle(model="offline", use_adjudicator=False,
                        global_matching=True, memory=None).run(case)
        self.assertEqual(result["matching"], {})
        self.assertEqual(len(result["exceptions"]), 2)

    def test_invalid_bank_total_is_exposed(self):
        case = Case("case", [invoice("A", 100)], [txn("R", 100)],
                    [BankLine("B", "2026-01-03", "", 90, ["R"])], [])
        result = Settle(model="offline", use_adjudicator=False,
                        global_matching=True, memory=None).run(case)
        self.assertFalse(result["bank_settlement_ok"])
        self.assertTrue(result["bank_settlement_errors"])

if __name__ == "__main__":
    unittest.main()
