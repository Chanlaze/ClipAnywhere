import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


class ExplorerTrayStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "send.log"
        self.source.write_text("Files/Folder sync uploaded\n", encoding="utf-8")
        namespace = runpy.run_path(str(Path(__file__).with_name("start_client_tray.pyw")))
        cls = namespace["TrayApp"]
        cls.__init__.__globals__["EXPLORER_LOG_PATH"] = self.source
        cls.__init__.__globals__["LOG_PATH"] = self.root / "client.log"
        self.app = cls()
        self.app.show_notification = Mock()

    def append(self, text):
        with self.source.open("a", encoding="utf-8") as log:
            log.write(text)

    def test_new_upload_notifies_once_and_skips_old_history(self):
        self.app.poll_explorer_output()
        self.app.show_notification.assert_not_called()
        self.append("Explorer send: uploading 2 files\nFiles/Folder sync uploaded\n")
        self.app.poll_explorer_output()
        self.app.poll_explorer_output()
        self.app.show_notification.assert_called_once_with(
            "ClipAnywhere sent", "Files/folders sent to other PCs.")
        self.assertIn("uploading 2 files", (self.root / "client.log").read_text())

    def test_partial_status_waits_for_newline(self):
        self.append("Files/Folder sync up")
        self.app.poll_explorer_output()
        self.app.show_notification.assert_not_called()
        self.append("loaded\n")
        self.app.poll_explorer_output()
        self.app.show_notification.assert_called_once()

    def test_failure_does_not_show_sent_notification(self):
        self.append("Explorer send failed\nConnection refused\n")
        self.app.poll_explorer_output()
        self.app.show_notification.assert_not_called()


if __name__ == "__main__":
    unittest.main()
