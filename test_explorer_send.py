import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import send_to_other


class ExplorerSendTests(unittest.TestCase):
    def test_parallel_explorer_invocations_form_one_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / name for name in ("first file.txt", "second.txt", "folder")]
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(
                    lambda p: send_to_other.collect_selection([p], root / "config.json", root / "queue.sqlite3"),
                    paths,
                ))
            batches = [batch for batch in results if batch]
            self.assertEqual(len(batches), 1)
            self.assertEqual(set(batches[0]), set(paths))

    def test_failure_is_logged_without_popup(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "send.log"
            with patch.object(send_to_other, "LOG_PATH", log), \
                 patch("sys.argv", ["send_to_other.py", "missing.txt"]), \
                 patch.object(send_to_other, "send_paths", side_effect=OSError("upload failed")):
                self.assertEqual(send_to_other.main(), 1)
            self.assertIn("upload failed", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
