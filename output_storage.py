"""output_storage.py - Xac dinh noi luu san pham cuoi (EPUB/PDF) theo he dieu hanh.

Tuan thu Android Scoped Storage (API 30+): tren Termux, di qua symlink
~/storage/shared/Documents (Termux tao khi chay `termux-setup-storage`) - day la
loi duy nhat de ghi file nguoi dung nhin thay tren app quan ly file/reader EPUB
ma khong can MANAGE_EXTERNAL_STORAGE.

Tren PC (Linux/macOS/Windows): dung ~/Documents/DichTruyen. Fallback ve thu muc
lam viec neu khong ghi duoc (vd Termux chua chay `termux-setup-storage`).

Sau khi copy, goi `termux-media-scan` de MediaStore quet lai ngay - file moi hien
tuc thi trong app doc EPUB/PDF ma khong can restart may.
"""
from __future__ import annotations

import os
import shutil
import subprocess

APP_SUBDIR = "DichTruyen"


def is_termux() -> bool:
    return ("com.termux" in os.environ.get("PREFIX", "")
            or os.path.isdir("/data/data/com.termux/files"))


def _candidates() -> list[str]:
    home = os.path.expanduser("~")
    if is_termux():
        # Uu tien Documents (goi la thu muc "sach" theo quy uoc Android), fallback
        # Downloads. Ca hai deu di qua symlink tao boi `termux-setup-storage`, do
        # do KHONG can MANAGE_EXTERNAL_STORAGE tren API 30+.
        return [
            os.path.join(home, "storage", "shared", "Documents"),
            os.path.join(home, "storage", "shared", "Download"),
            os.path.join(home, "storage", "downloads"),
            os.path.join(home, "storage", "shared"),
        ]
    return [
        os.path.join(home, "Documents"),
        os.path.join(home, "Desktop"),
        home,
    ]


def user_documents_dir() -> str | None:
    """Tra ve thu muc Documents user-visible dau tien co the ghi duoc; None neu khong co."""
    for c in _candidates():
        if os.path.isdir(c) and os.access(c, os.W_OK):
            return c
    return None


def output_dir(create: bool = True) -> str | None:
    """Tra ve thu muc dich (co subdir 'DichTruyen'), tao neu chua co (create=True).
    Tra ve None neu khong co thu muc goc phu hop hoac khong tao duoc subdir.
    """
    base = user_documents_dir()
    if not base:
        return None
    target = os.path.join(base, APP_SUBDIR)
    if os.path.isdir(target):
        return target
    if not create:
        return None
    try:
        os.makedirs(target, exist_ok=True)
        return target
    except OSError:
        # Fallback ve base neu khong tao duoc subdir (vd read-only, quota)
        return base


def save_output_file(src_path: str, move: bool = False) -> tuple[str, str | None]:
    """Copy (mac dinh) hoac move file src sang thu muc user-visible; goi MediaStore
    scan tren Termux de file hien ngay trong app quan ly file.

    Tra ve (final_path, warning_msg). final_path la src_path neu khong luu duoc
    (khi do warning_msg giai thich ly do).
    """
    if not os.path.isfile(src_path):
        raise FileNotFoundError(src_path)
    dest_dir = output_dir()
    if not dest_dir:
        return src_path, ("Chua co thu muc Documents user-visible - "
                          + ("hay chay `termux-setup-storage` trong Termux."
                             if is_termux() else "kiem tra quyen ghi ~/Documents."))
    dest_path = os.path.join(dest_dir, os.path.basename(src_path))
    if os.path.abspath(src_path) == os.path.abspath(dest_path):
        _termux_media_scan(dest_path)
        return dest_path, None
    try:
        op = shutil.move if move else shutil.copy2
        op(src_path, dest_path)
    except OSError as e:
        return src_path, f"Khong copy duoc sang {dest_dir}: {e}"
    _termux_media_scan(dest_path)
    return dest_path, None


def _termux_media_scan(path: str) -> None:
    """Yeu cau MediaStore quet lai file (chi Termux/Android). Neu khong co
    `termux-media-scan` (chua cai Termux:API) thi im lang bo qua - file van luu
    duoc, chi la co the phai cho Android scan lai sau vai phut."""
    if not is_termux():
        return
    if shutil.which("termux-media-scan") is None:
        return
    try:
        subprocess.run(["termux-media-scan", "-r", path],
                       check=False, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
