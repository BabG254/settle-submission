"""Exercise alias-memory persistence and the documented synthetic tariff."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from settle.fees import fee_for, max_fee_upto
from settle.memory import AliasMemory


class FeeTests(unittest.TestCase):
    def test_free_first_band(self):
        self.assertEqual(fee_for(100), 0)

    def test_band_boundary(self):
        self.assertEqual(fee_for(500), 8)
        self.assertEqual(fee_for(501), 15)

    def test_max_fee_is_an_upper_bound(self):
        for gross in (100, 500, 1_000, 10_000, 100_000):
            self.assertGreaterEqual(max_fee_upto(gross), fee_for(gross))


class MemoryTests(unittest.TestCase):
    def test_approved_alias_persists_without_duplicate_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aliases.db"
            memory = AliasMemory(path)
            self.assertTrue(memory.remember(
                "MAMA NJERI GROCERS", "C-1", "Njeri Wambui",
                "human_approval", "Reviewed against invoice INV-1",
            ))
            self.assertEqual(memory.lookup("Mama Njeri Grocers"), "C-1")
            self.assertFalse(memory.remember(
                "MAMA NJERI GROCERS", "C-1", "Njeri Wambui",
                "human_approval", "Repeated confirmation",
            ))
            self.assertEqual(memory.size(), 1)
            memory.conn.close()
            reopened = AliasMemory(path)
            self.assertEqual(reopened.lookup("MAMA NJERI GROCERS"), "C-1")
            reopened.conn.close()


if __name__ == "__main__":
    unittest.main()
