"""POSIX advisory lock regression tests."""
import os
import tempfile
import unittest
from pathlib import Path

from settle.approval_safety import locked_prediction


@unittest.skipUnless(os.name == "posix", "fcntl is POSIX-only")
class LockingTests(unittest.TestCase):
    def test_context_releases_file_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pred.json"
            with locked_prediction(path):
                self.assertTrue(path.with_name("pred.json.lock").exists())
            # A second sequential acquisition must succeed after release.
            with locked_prediction(path):
                self.assertTrue(path.with_name("pred.json.lock").exists())


if __name__ == "__main__":
    unittest.main()
