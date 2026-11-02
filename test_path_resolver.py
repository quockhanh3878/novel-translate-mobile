"""test_path_resolver.py - Kiem tra module path_resolver.

Kiem tra:
- sanitize_filename
- validate_output_dir
- resolve_pipeline_paths
- is_safe_path
- safe_upload_file
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT)

from path_resolver import (
    sanitize_filename,
    validate_output_dir,
    resolve_pipeline_paths,
    is_safe_path,
    safe_upload_file,
)


class TestPathResolver(unittest.TestCase):
    def test_sanitize_filename(self):
        # Kiem tra ky tu cam tren Windows
        self.assertEqual(sanitize_filename('Ten:Truyen*Mau?1"2<3>4|5/6\\7'), "Ten_Truyen_Mau_1_2_3_4_5_6_7")
        # Giu nguyen tieng Viet co dau va khoang trang
        self.assertEqual(sanitize_filename("Đệ Tam Trùng Nhân Cách"), "Đệ Tam Trùng Nhân Cách")
        # Xu ly chuoi rong hoac chi co khoang trang / dau cham
        self.assertEqual(sanitize_filename("   ...   "), "truyen")
        self.assertEqual(sanitize_filename("", default="mac_dinh"), "mac_dinh")

    def test_validate_output_dir_default(self):
        # Khi khong truyen gi, tra ve True va thu muc cwd
        ok, path, err = validate_output_dir("")
        self.assertTrue(ok)
        self.assertEqual(path, Path.cwd().resolve())
        self.assertEqual(err, "")

        ok, path, err = validate_output_dir(None)
        self.assertTrue(ok)
        self.assertEqual(path, Path.cwd().resolve())

    def test_validate_output_dir_custom_and_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            # Thu muc tieng Viet co dau va khoang trang
            target = tmp_p / "Thư mục xuất kết quả" / "Bộ truyện 1"
            ok, path, err = validate_output_dir(str(target), create=True)
            self.assertTrue(ok)
            self.assertTrue(path.is_dir())
            self.assertEqual(path, target.resolve())

    def test_validate_output_dir_invalid_chars(self):
        # Ky tu cam trong ten thu muc
        ok, path, err = validate_output_dir("thu_muc*nguy_hiem")
        self.assertFalse(ok)
        self.assertIn("chua ky tu khong hop le", err)

    def test_resolve_pipeline_paths_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            # 1. Nhap URL khong chon noi luu
            res = resolve_pipeline_paths("https://example.com/dau-pha_1.html", title="Đấu Phá", cwd=cwd)
            self.assertTrue(res["is_url"])
            self.assertFalse(res["has_custom_output"])
            self.assertEqual(res["raw_path"], cwd / "Dau Pha_raw.txt")
            self.assertEqual(res["translated_path"], cwd / "Dau Pha_raw.txt.viet.txt")
            self.assertEqual(res["epub_path"], cwd / "Đấu Phá.epub")
            self.assertEqual(res["output_dir"], cwd)
            self.assertEqual(res["pdf_path"].parent, cwd)
            self.assertEqual(res["pdf_path"].suffix, ".pdf")

            # 2. File .txt khong chon noi luu
            raw_input = cwd / "truyen_goc.txt"
            raw_input.write_text("noi dung", encoding="utf-8")
            res_txt = resolve_pipeline_paths(str(raw_input), title="Đấu Phá", cwd=cwd)
            self.assertFalse(res_txt["is_url"])
            self.assertFalse(res_txt["has_custom_output"])
            self.assertEqual(res_txt["raw_path"], raw_input)
            self.assertEqual(res_txt["translated_path"], cwd / "truyen_goc.txt.viet.txt")
            self.assertEqual(res_txt["epub_path"], cwd / "Đấu Phá.epub")

    def test_resolve_pipeline_paths_custom_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            custom_out = cwd / "KetQuaXuat"

            # 1. Nhap URL co chon noi luu -> ca raw, translated, epub luu o custom_out
            res = resolve_pipeline_paths("https://example.com/dau-pha_1.html", title="Đấu Phá", output_dir=custom_out, cwd=cwd)
            self.assertTrue(res["is_url"])
            self.assertTrue(res["has_custom_output"])
            self.assertEqual(res["raw_path"], custom_out.resolve() / "Dau Pha_raw.txt")
            self.assertEqual(res["translated_path"], custom_out.resolve() / "Dau Pha_raw.txt.viet.txt")
            self.assertEqual(res["epub_path"], custom_out.resolve() / "Đấu Phá.epub")
            self.assertEqual(res["output_dir"], custom_out.resolve())
            self.assertEqual(res["pdf_path"].parent, custom_out.resolve())
            self.assertEqual(res["pdf_path"].suffix, ".pdf")

            # 2. File .txt co chon noi luu -> raw giu nguyen, translated va epub luu o custom_out
            source_dir = cwd / "NguonNgoai"
            source_dir.mkdir()
            raw_file = source_dir / "truyen_ngoai.txt"
            raw_file.write_text("noi dung", encoding="utf-8")

            res_txt = resolve_pipeline_paths(str(raw_file), title="Truyện Ngoài", output_dir=custom_out, cwd=cwd)
            self.assertFalse(res_txt["is_url"])
            self.assertTrue(res_txt["has_custom_output"])
            self.assertEqual(res_txt["raw_path"], raw_file)
            self.assertEqual(res_txt["translated_path"], custom_out.resolve() / "truyen_ngoai.txt.viet.txt")
            self.assertEqual(res_txt["epub_path"], custom_out.resolve() / "Truyện Ngoài.epub")

    def test_resolve_pipeline_paths_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            url = "https://example.com/dau-pha_1.html"
            legacy = cwd / "Tên Cũ_raw.txt"
            legacy.write_text("legacy content", encoding="utf-8")

            # Khi co file cu ten "Tên Cũ_raw.txt" va truyen title="Tên Cũ", uu tien giu file cu
            res = resolve_pipeline_paths(url, title="Tên Cũ", cwd=cwd)
            self.assertEqual(res["raw_path"], legacy)

    def test_guess_title_and_resolve_consistent_package_names(self):
        from crawler import guess_title

        url = "https://www.wa01.com/novel/pagea/qingshan-huishuohuadezhouzi_1.html"
        raw_win = r"F:\Clone\novel-translate-mobile\Qingshan Huishuohuadezhouzi_raw.txt"
        raw_rel = "Qingshan Huishuohuadezhouzi_raw.txt"
        viet_rel = "Qingshan Huishuohuadezhouzi_raw.txt.viet.txt"

        self.assertEqual(guess_title(url), "Qingshan Huishuohuadezhouzi")
        self.assertEqual(guess_title(raw_win), "Qingshan Huishuohuadezhouzi")
        self.assertEqual(guess_title(raw_rel), "Qingshan Huishuohuadezhouzi")
        self.assertEqual(guess_title(viet_rel), "Qingshan Huishuohuadezhouzi")

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            res_url = resolve_pipeline_paths(url, title="", cwd=cwd)
            res_raw = resolve_pipeline_paths(str(cwd / raw_rel), title="", cwd=cwd)
            self.assertEqual(res_url["epub_path"], cwd / "Qingshan Huishuohuadezhouzi.epub")
            self.assertEqual(res_raw["epub_path"], cwd / "Qingshan Huishuohuadezhouzi.epub")
            self.assertEqual(res_url["pdf_path"], cwd / "Qingshan Huishuohuadezhouzi.pdf")
            self.assertEqual(res_raw["pdf_path"], cwd / "Qingshan Huishuohuadezhouzi.pdf")

    def test_guess_title_and_resolve_adapter_urls(self):
        from crawler import guess_title

        pairs = [
            ("https://www.uukanshu.cc/book/11966/", "https://www.uukanshu.cc/book/11966/7353294.html", "11966"),
            ("https://www.bgq99.cc/book/1217966/", "https://www.bgq99.cc/book/1217966/1.html", "1217966"),
            ("https://www.69shuba.com/book/90175.htm", "https://www.69shuba.com/txt/90175/40620030", "90175"),
            ("https://www.shubaow.net/book/378.html", "https://www.shubaow.net/book/378/140651.html", "378"),
            ("https://www.biquge.tw/book/200183/", "https://www.biquge.tw/book/200183/75125892.html", "200183"),
            ("https://www.tianyabooks.com/net/csx_03/", "https://www.tianyabooks.com/net/csx_03/27174.html", "Csx 03"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            for catalog_url, chapter_url, expected_title in pairs:
                self.assertEqual(guess_title(catalog_url), expected_title)
                self.assertEqual(guess_title(chapter_url), expected_title)
                res_cat = resolve_pipeline_paths(catalog_url, title="", cwd=cwd)
                res_ch = resolve_pipeline_paths(chapter_url, title="", cwd=cwd)
                self.assertEqual(res_cat["raw_path"], res_ch["raw_path"])
                self.assertEqual(res_cat["epub_path"], res_ch["epub_path"])
                self.assertEqual(res_cat["pdf_path"], res_ch["pdf_path"])

    def test_is_safe_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            allowed = root / "safe_dir"
            allowed.mkdir()
            safe_file = allowed / "file.txt"
            safe_file.write_text("ok", encoding="utf-8")

            # File nam trong thu muc cho phep
            self.assertTrue(is_safe_path(safe_file, [allowed]))

            # Thu muc con ben trong thu muc cho phep
            sub_dir = allowed / "sub"
            sub_dir.mkdir()
            self.assertTrue(is_safe_path(sub_dir / "sub_file.txt", [allowed]))

            # Path traversal vuot ra ngoai thu muc cho phep
            danger = allowed / ".." / "outside.txt"
            self.assertFalse(is_safe_path(danger, [allowed]))

    def test_safe_upload_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp) / "uploads"
            data = "Noi dung truyen tai len".encode("utf-8")
            ok, final_path, err = safe_upload_file(upload_dir, "truyen_moi.txt", data)
            self.assertTrue(ok)
            self.assertTrue(final_path.is_file())
            self.assertEqual(final_path.read_bytes(), data)
            self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
