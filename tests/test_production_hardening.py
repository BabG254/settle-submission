import json
import tempfile
import unittest
from pathlib import Path
from settle.locking import file_lock
from settle.privacy import redact
from settle.benchmark import benchmark
from settle.recovery import recover_approvals
from settle.schema import Case, Invoice, Txn, write_case


class HardeningTests(unittest.TestCase):
    def test_portable_lock_can_be_reacquired(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lock"
            with file_lock(p):
                self.assertTrue(p.exists())
            with file_lock(p):
                pass

    def test_sensitive_fields_are_masked(self):
        redacted = redact("0722123456 test@example.com sk-ant-abcdefghijklmno")
        self.assertNotIn("0722123456", redacted)
        self.assertNotIn("test@example.com", redacted)
        self.assertNotIn("sk-ant-abcdefghijklmno", redacted)

    def test_benchmark_has_explicit_limit(self):
        with self.assertRaises(ValueError):
            benchmark(5001)
        result = benchmark(2)
        self.assertEqual(result["invoices"], 2)

    def test_approval_recovery_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = Case("case", [Invoice("I", "C", "Grace", 100, "2026-01-01", "2026-01-10")],
                        [Txn("R", "2026-01-02T12:00:00", "pay_bill", "Grace", "",
                             100, 0, 0, "")], [], [])
            write_case(case, root / "data", {"I": ["R"]})
            pred = root / "pred.json"
            pred.write_text(json.dumps({"case_id": "case", "matching": {"I": ["R"]},
                "human_approvals": [{"invoice_id": "I", "receipts": ["R"]}]}))
            db = root / "aliases.db"
            self.assertEqual(recover_approvals(pred, root / "data", db)["aliases_recovered"], 1)
            self.assertEqual(recover_approvals(pred, root / "data", db)["aliases_recovered"], 0)


if __name__ == "__main__":
    unittest.main()
