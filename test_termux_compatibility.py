"""test_termux_compatibility.py - Kiem tra tinh tuong thich tren moi truong Termux Android.

Kiem tra:
- Cu phap va tinh hop le cua setup_termux.sh, run_termux.sh, update_termux.sh.
- Ho tro pip --break-system-packages tren Python 3.12+ Termux.
- Co che tu dong du doan ten truyen trong run_termux.sh.
- Co che termux-wake-lock va termux-wake-unlock.
- Thong bao Android qua termux-notification khi dich xong hoac loi.
- Tu dong phat hien va xuat file EPUB ra bo nho ngoai Android (Documents/Download).
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT)

import web_gui


class TestTermuxCompatibility(unittest.TestCase):
    def test_shell_scripts_syntax_and_patterns(self):
        scripts = ["setup_termux.sh", "run_termux.sh", "update_termux.sh"]
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.isfile(git_bash):
            cmd = [git_bash, "-n"] + [os.path.join(PROJECT, s) for s in scripts]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Loi cu phap bash: {res.stderr}")

        # Kiem tra noi dung setup_termux.sh va update_termux.sh co co --break-system-packages phong ngua PEP 668
        for s in ["setup_termux.sh", "update_termux.sh"]:
            content = Path(PROJECT, s).read_text(encoding="utf-8")
            self.assertIn("--break-system-packages", content, f"{s} can co ho tro --break-system-packages cho Termux moi")

        # Kiem tra run_termux.sh co co che ho tro tieu de tu dong khi TITLE rong
        run_content = Path(PROJECT, "run_termux.sh").read_text(encoding="utf-8")
        self.assertIn("guess_title", run_content, "run_termux.sh can ho tro guess_title khi nguoi dung de trong tieu de")

    def test_termux_wake_lock_and_unlock(self):
        with patch.object(web_gui, "_IS_TERMUX", True):
            with patch("subprocess.run") as mock_run:
                web_gui._termux_wake_lock()
                mock_run.assert_called_with(
                    ["termux-wake-lock"],
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                mock_run.reset_mock()
                web_gui._termux_wake_unlock()
                mock_run.assert_called_with(
                    ["termux-wake-unlock"],
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                # Kiem tra an toan khi gap loi ngoai le
                mock_run.side_effect = OSError("Khong co lenh")
                web_gui._termux_wake_lock()
                web_gui._termux_wake_unlock()

    def test_termux_notification(self):
        # 1. Khi la Termux, phai goi termux-notification
        with patch.object(web_gui, "_IS_TERMUX", True):
            with patch("subprocess.run") as mock_run:
                getattr(web_gui, "_termux_notify")("Tieu de", "Noi dung thong bao")
                mock_run.assert_called_with(
                    ["termux-notification", "-t", "Tieu de", "-c", "Noi dung thong bao"],
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                # Ngoai le khong gay crash
                mock_run.side_effect = Exception("Loi notification")
                getattr(web_gui, "_termux_notify")("Tieu de", "Noi dung")

        # 2. Khi khong phai Termux, khong goi subprocess
        with patch.object(web_gui, "_IS_TERMUX", False):
            with patch("subprocess.run") as mock_run:
                getattr(web_gui, "_termux_notify")("Tieu de", "Noi dung")
                mock_run.assert_not_called()

    def test_termux_storage_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            fake_epub = tmp_root / "test_novel.epub"
            fake_epub.write_bytes(b"fake epub content")

            # Gia lap thu muc Documents tren Android (storage/shared da ton tai)
            fake_docs = tmp_root / "storage" / "shared" / "Documents"
            fake_docs.parent.mkdir(parents=True, exist_ok=True)
            with patch.object(web_gui, "SHARED_DOCUMENTS", str(fake_docs)):
                dest = getattr(web_gui, "_export_to_android_storage")(str(fake_epub))
                self.assertIsNotNone(dest)
                self.assertTrue(os.path.isfile(dest))
                self.assertEqual(Path(dest).read_bytes(), b"fake epub content")

            # Gia lap khi storage chua duoc cap quyen (thu muc goc khong ton tai)
            with patch.object(web_gui, "SHARED_DOCUMENTS", str(tmp_root / "nonexistent" / "Documents")):
                with patch("os.path.exists", return_value=False):
                    dest_none = getattr(web_gui, "_export_to_android_storage")(str(fake_epub))
                    self.assertIsNone(dest_none)


if __name__ == "__main__":
    unittest.main()
