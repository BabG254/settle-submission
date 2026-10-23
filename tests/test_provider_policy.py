"""Independent synthetic fixtures for configurable settlement rules."""
import unittest
from settle.provider_policy import SettlementPolicy, verify_provider_batch
from settle.schema import BankLine, Txn

class PolicyTests(unittest.TestCase):
    def test_no_adjustment(self):
        tx = Txn("R", "2026-01-02T10:00:00", "pay_bill", "Redacted", "",
                 95, 5, 0, "")
        self.assertEqual(verify_provider_batch(
            BankLine("B", "2026-01-03", "synthetic", 95, ["R"]),
            [tx], SettlementPolicy("synthetic-net")), [])

    def test_configured_batch_adjustment(self):
        tx = Txn("R", "2026-01-02T10:00:00", "pay_bill", "Redacted", "",
                 95, 5, 0, "")
        self.assertEqual(verify_provider_batch(
            BankLine("B", "2026-01-03", "synthetic", 92, ["R"]),
            [tx], SettlementPolicy("synthetic-adjusted", fixed_batch_adjustment=3)), [])

    def test_unverified_delay_fails(self):
        tx = Txn("R", "2026-01-02T10:00:00", "pay_bill", "Redacted", "",
                 95, 5, 0, "")
        self.assertTrue(verify_provider_batch(
            BankLine("B", "2026-01-10", "synthetic", 95, ["R"]),
            [tx], SettlementPolicy("synthetic-net", max_lag_days=3)))
