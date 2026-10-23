"""Human approval guardrails and atomic file persistence."""
import json
import tempfile
import unittest
from pathlib import Path

from settle.approval_safety import ApprovalError, atomic_write_json, validate_approval
from settle.schema import Case, Invoice, Txn


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        invoice = Invoice("I", "C", "Grace", 100, "2026-01-01", "2026-01-10")
        receipt = Txn("R", "2026-01-02T10:00:00", "pay_bill", "Grace", "",
                      100, 0, 0, "")
        self.case = Case("case", [invoice], [receipt], [], [])
        self.pred = {"matching": {}, "exceptions": [{"invoice_id": "I"}]}

    def test_valid_approval_removes_exception(self):
        result = validate_approval(self.pred, self.case, "I", ["R"])
        self.assertEqual(result["matching"]["I"], ["R"])
        self.assertEqual(result["exceptions"], [])
        self.assertEqual(self.pred["matching"], {})

    def test_replay_rejected(self):
        result = validate_approval(self.pred, self.case, "I", ["R"])
        with self.assertRaises(ApprovalError):
            validate_approval(result, self.case, "I", ["R"])

    def test_duplicate_receipts_rejected(self):
        with self.assertRaises(ApprovalError):
            validate_approval(self.pred, self.case, "I", ["R", "R"])

    def test_missing_receipt_rejected(self):
        with self.assertRaises(ApprovalError):
            validate_approval(self.pred, self.case, "I", ["NOT_PRESENT"])

    def test_atomic_json_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pred.json"
            atomic_write_json(path, {"matching": {"I": ["R"]}})
            self.assertEqual(json.loads(path.read_text())["matching"]["I"], ["R"])


if __name__ == "__main__":
    unittest.main()
