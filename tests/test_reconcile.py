"""Independent examples of global ambiguity and settlement integrity."""
import unittest
from settle.reconcile import unique_global_matches, verify_settlements
from settle.schema import BankLine, Invoice, Txn


def invoice(i, amount):
    return Invoice(i, i, "Grace Njeri", amount, "2026-01-01", "2026-01-10")


def txn(ref, net, kind="pay_bill", reverses=None):
    return Txn(ref, "2026-01-02T12:00:00", kind, "Grace Njeri",
               "2547*****100", net, 0, 0, "", reverses)


class GlobalMatchingTests(unittest.TestCase):
    def test_uncontested_exact_match(self):
        self.assertEqual(unique_global_matches([invoice("A", 100)],
                                               [txn("R", 100)]), {"A": ["R"]})

    def test_ambiguous_identity_is_not_guessed(self):
        self.assertEqual(unique_global_matches(
            [invoice("A", 100), invoice("B", 100)], [txn("R", 100)]), {})

    def test_disjoint_payments_are_retained(self):
        self.assertEqual(unique_global_matches(
            [invoice("A", 100), invoice("B", 200)],
            [txn("R1", 100), txn("R2", 200)]),
            {"A": ["R1"], "B": ["R2"]})

    def test_budget_fails_closed(self):
        self.assertEqual(unique_global_matches([invoice("A", 100)],
                                               [txn("R", 100)], maximum_nodes=0), {})


class SettlementTests(unittest.TestCase):
    def test_valid_net_settlement(self):
        self.assertTrue(verify_settlements(
            [BankLine("B", "2026-01-03", "batch", 95, ["R"])],
            [Txn("R", "2026-01-02T12:00:00", "pay_bill", "G", "",
                 95, 5, 0, "")]).ok)

    def test_wrong_amount_rejected(self):
        self.assertFalse(verify_settlements(
            [BankLine("B", "2026-01-03", "batch", 90, ["R"])],
            [txn("R", 100)]).ok)

    def test_duplicate_allocation_rejected(self):
        self.assertFalse(verify_settlements(
            [BankLine("B1", "2026-01-03", "", 100, ["R"]),
             BankLine("B2", "2026-01-03", "", 100, ["R"])],
            [txn("R", 100)]).ok)

    def test_unlinked_bank_line_unverified(self):
        self.assertFalse(verify_settlements(
            [BankLine("B", "2026-01-03", "", 100, [])], [txn("R", 100)]).ok)

    def test_reversal_rejected(self):
        self.assertFalse(verify_settlements(
            [BankLine("B", "2026-01-03", "", 100, ["R"])],
            [txn("R", 100), txn("REV", 0, "reversal", "R")]).ok)


if __name__ == "__main__":
    unittest.main()
