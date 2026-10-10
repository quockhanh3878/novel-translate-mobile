"""path_resolver.py - Xu ly duong dan thong nhat va bao mat cho novel-translate.

Dam bao:
- Chuan hoa duong dan (Path.resolve).
- Chon thu muc dau ra (mac dinh data_dir hoac thu muc tuy chon).
- Chuyen huong file tho, ban dich, EPUB, glossary theo dung quy uoc.
- Chuyen ten file an toan tren Windows / Linux / Termux (chong ky tu cam, giu tieng Viet va khoang trang).
- Chong path traversal (../, ..\\).
- Ghi file tai len theo co che nguyen tu (atomic write qua file tam).
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path


# Cac ky tu cam trong ten file tren he dieu hanh Windows
WINDOWS_FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str, default: str = "truyen") -> str:
    """Loai bo ky tu cam, giu lai chu cai (ke ca tieng Viet co dau), so va khoang trang."""
    cleaned = WINDOWS_FORBIDDEN_CHARS.sub("_", name or "")
    cleaned = cleaned.strip(". ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or default


def validate_output_dir(dir_path: str | Path | None, create: bool = True) -> tuple[bool, Path | None, str]:
    """Kiem tra va chuan hoa thu muc dau ra.
    
    Neu dir_path rong: mac dinh tra ve thu muc lam viec hien tai (Path.cwd()).
    Neu dir_path co gia tri:
    - Kiem tra path traversal nguy hiem hoac ky tu khong hop le.
    - Tao thu muc neu chua ton tai (khi create=True).
    - Kiem tra quyen ghi bang cach tao file tam probe.
    """
    if not dir_path or not str(dir_path).strip():
        cwd = Path.cwd().resolve()
        return True, cwd, ""

    raw_str = str(dir_path).strip()
    # Kiem tra ky tu cam cua ten thu muc (tru dau phan cach o dia va dau gach cheo)
    path_without_drive = raw_str[2:] if len(raw_str) >= 2 and raw_str[1] == ":" else raw_str
    if re.search(r'[*?"<>|]', path_without_drive):
        return False, None, f"Duong dan chua ky tu khong hop le: {raw_str}"

    try:
        resolved = Path(raw_str).expanduser().resolve()
    except Exception as exc:
        return False, None, f"Duong dan khong hop le: {exc}"

    if create and not resolved.exists():
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, None, f"Khong the tao thu muc: {exc}"

    if not resolved.is_dir():
        return False, None, f"Duong dan khong phai la thu muc: {resolved}"

    # Kiem tra quyen ghi thuc te
    probe_file = resolved / f".write_probe_{os.getpid()}_{id(dir_path)}.tmp"
    try:
        probe_file.write_text("probe", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
    except OSError as exc:
        return False, None, f"Khong co quyen ghi vao thu muc: {exc}"

    return True, resolved, ""


def resolve_pipeline_paths(
    input_val: str,
    title: str = "",
    output_dir: str | Path | None = None,
    cwd: Path | None = None,
) -> dict:
    """Xac dinh toan bo bo duong dan chuan hoa cho pipeline.
    
    Quy uoc:
    - Khong chon noi luu (output_dir rong):
      + URL: raw, translated (.viet.txt), epub nam tai thu muc mac dinh (cwd).
      + File .txt: translated va epub nam tai thu muc mac dinh (cwd).
    - Co chon noi luu (output_dir hop le):
      + URL: ca raw, translated va epub luu tai output_dir.
      + File .txt: raw giu nguyen vi tri, translated va epub luu tai output_dir.
    """
    base_cwd = (cwd or Path.cwd()).resolve()
    has_custom_output = bool(output_dir and str(output_dir).strip())
    
    if has_custom_output:
        ok, out_path, err = validate_output_dir(output_dir, create=True)
        if not ok or out_path is None:
            raise ValueError(err)
        target_dir = out_path
    else:
        target_dir = base_cwd

    input_trimmed = (input_val or "").strip()
    is_url = input_trimmed.lower().startswith(("http://", "https://"))

    safe_title = sanitize_filename(title) if title else "truyen"

    if is_url:
        try:
            from crawler import guess_title
            url_slug = guess_title(input_trimmed)
        except Exception:
            url_slug = safe_title
        url_name = f"{sanitize_filename(url_slug)}_raw.txt"
        target_url_file = target_dir / url_name

        if target_url_file.is_file():
            raw_path = target_url_file
        else:
            legacy_name = f"{safe_title}_raw.txt" if title.strip() else ""
            target_legacy_file = target_dir / legacy_name if legacy_name else None
            if target_legacy_file and target_legacy_file != target_url_file and target_legacy_file.is_file():
                raw_path = target_legacy_file
            else:
                raw_path = target_url_file
    else:
        raw_p = Path(input_trimmed).expanduser()
        if not raw_p.is_absolute():
            raw_p = (base_cwd / raw_p).resolve()
        else:
            raw_p = raw_p.resolve()
        raw_path = raw_p

    # Duong dan file dich va EPUB
    if has_custom_output:
        translated_path = target_dir / f"{raw_path.name}.viet.txt"
        epub_path = target_dir / f"{safe_title}.epub"
    else:
        # Tuong thich tuyet doi voi quy uoc cu khi khong chon noi luu
        translated_path = base_cwd / f"{raw_path.name}.viet.txt" if not is_url else base_cwd / f"{raw_path.name}.viet.txt"
        epub_path = base_cwd / f"{safe_title}.epub"

    # Duong dan cac file bo tro
    style_path = Path(f"{str(translated_path).rsplit('.', 1)[0]}_style.txt")

    return {
        "is_url": is_url,
        "title": title or safe_title,
        "safe_title": safe_title,
        "raw_path": raw_path,
        "translated_path": translated_path,
        "epub_path": epub_path,
        "style_path": style_path,
        "output_dir": target_dir,
        "has_custom_output": has_custom_output,
    }


def is_safe_path(target_path: str | Path, allowed_dirs: list[str | Path]) -> bool:
    """Kiem tra xem target_path co nam trong bat ky thu muc cho phep nao hay khong (chong path traversal)."""
    try:
        resolved_target = Path(target_path).expanduser().resolve()
    except (OSError, ValueError):
        return False

    for allowed in allowed_dirs:
        try:
            resolved_allowed = Path(allowed).expanduser().resolve()
            resolved_target.relative_to(resolved_allowed)
            return True
        except (ValueError, OSError):
            continue
    return False


def safe_upload_file(upload_dir: str | Path, filename: str, data: bytes) -> tuple[bool, Path | None, str]:
    """Luu file tai len bang co che ghi tam thoi (.tmp) roi doi ten nguyen tu (atomic)."""
    try:
        dest_dir = Path(upload_dir).expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_filename(filename, default="file_tai_len.txt")
        final_path = dest_dir / safe_name

        fd, tmp_path_str = tempfile.mkstemp(dir=str(dest_dir), prefix="upl_", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)

        os.replace(tmp_path_str, final_path)
        return True, final_path, ""
    except Exception as exc:
        return False, None, f"Loi luu file tai len: {exc}"
