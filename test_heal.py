"""Tu sua file truyen: bo chuong trung, sap lai thu tu, chuong da dich khong dich lai.

Chay: python test_heal.py
"""

import os
import tempfile

import deepseek_translate as dt
from crawler import CHAPTER_SEP, parse_chapters


def write(path, entries, head="TRUYỆN", head_sep=False):
    with open(path, "w", encoding="utf-8") as f:
        if head:
            f.write(f"=== {head} ===\n\n" + (CHAPTER_SEP if head_sep else ""))
        for title, paras in entries:
            f.write(f"=== {title} ===\n\n" + "".join(f"{p}\n\n" for p in paras) + CHAPTER_SEP)


def raw_ch(n):
    return (f"第{n}章", [f"原文{n}a", f"原文{n}b"])


def tr_ch(n):
    return (f"Chương {n}: Ten {n}", [f"Viet {n}a", f"Viet {n}b"])


def titles(path):
    return [c["title"] for c in parse_chapters(path)]


def fake_api(calls):
    def _fake(chapter, *a, chapter_idx=None, **k):
        calls.append(chapter["title"])
        return {"title": "Moi", "paragraphs": ["Dich moi a", "Dich moi b"], "new_terms": {},
                "idioms": {}, "term_warnings": [], "usage": {}}
    return _fake


def test_heal_duplicates_and_order_then_translate_only_missing():
    with tempfile.TemporaryDirectory() as d:
        raw, out = os.path.join(d, "raw.txt"), os.path.join(d, "raw.txt.viet.txt")
        # File cu: thieu chuong 4 (cao bu sau o cuoi), chuong 5 bi cao trung, co thong bao sau chuong 2.
        notice = ("今天晚更", ["稍後更新"])
        write(raw, [raw_ch(1), raw_ch(2), notice, raw_ch(3), raw_ch(5), raw_ch(6), raw_ch(5), raw_ch(4)])
        write(out, [tr_ch(1), tr_ch(2), ("Ra muộn", ["Cập nhật sau"]), tr_ch(3), tr_ch(5), tr_ch(6),
                    tr_ch(5)], head="Truyện", head_sep=True)

        assert dt.heal_novel(raw, out, log=lambda *_: None)
        assert titles(raw) == ["TRUYỆN", "第1章", "第2章", "今天晚更", "第3章", "第4章", "第5章", "第6章"]
        # File dich chi giu phan lien tuc; chuong 5, 6 da dich cho san
        assert titles(out) == ["Truyện", "Chương 1: Ten 1", "Chương 2: Ten 2", "Ra muộn", "Chương 3: Ten 3"]
        assert os.path.exists(raw + ".truoc-sua.bak") and os.path.exists(out + ".truoc-sua.bak")
        assert not dt.heal_novel(raw, out, log=lambda *_: None)  # chay lai: khong con gi de sua

        calls, original = [], dt.translate_chapter
        dt.translate_chapter = fake_api(calls)
        try:
            dt.translate_novel(raw, out, None, "k", style_detect=False, prepare=False,
                               avoid_peak=False, log=lambda *_: None)
        finally:
            dt.translate_chapter = original
        assert calls == ["第4章"], calls  # chi chuong thieu moi goi API
        chapters = parse_chapters(out)
        assert [c["title"] for c in chapters] == ["Truyện", "Chương 1: Ten 1", "Chương 2: Ten 2", "Ra muộn",
                                                  "Chương 3: Ten 3", "Chương 4: Moi", "Chương 5: Ten 5",
                                                  "Chương 6: Ten 6"], chapters
        assert chapters[6]["paragraphs"] == ["Viet 5a", "Viet 5b"]
        assert not os.path.exists(dt._stash_path(out))
    print("PASS tu sua: bo trung, sap lai thu tu, chi dich chuong thieu, ban dich cu giu nguyen")


def test_stream_uses_stash():
    from crawler import iter_chapters_from_file
    with tempfile.TemporaryDirectory() as d:
        raw, out = os.path.join(d, "raw.txt"), os.path.join(d, "raw.txt.viet.txt")
        write(raw, [raw_ch(1), raw_ch(3), raw_ch(2)])
        write(out, [tr_ch(1), tr_ch(3)], head="Truyện", head_sep=True)
        assert dt.heal_novel(raw, out, log=lambda *_: None)
        calls, original = [], dt.translate_chapter
        dt.translate_chapter = fake_api(calls)
        try:
            dt.translate_novel_stream(iter_chapters_from_file(raw), out, None, "k",
                                      avoid_peak=False, log=lambda *_: None)
        finally:
            dt.translate_chapter = original
        assert calls == ["第2章"], calls
        assert titles(out) == ["Truyện", "Chương 1: Ten 1", "Chương 2: Moi", "Chương 3: Ten 3"], titles(out)
    print("PASS stream: chuong da dich cho san khong goi API")


def test_translate_novel_heals_by_itself():
    with tempfile.TemporaryDirectory() as d:
        raw, out = os.path.join(d, "raw.txt"), os.path.join(d, "raw.txt.viet.txt")
        write(raw, [raw_ch(1), raw_ch(3), raw_ch(3), raw_ch(2)])
        write(out, [tr_ch(1), tr_ch(3)], head="Truyện", head_sep=True)
        calls, original = [], dt.translate_chapter
        dt.translate_chapter = fake_api(calls)
        try:
            dt.translate_novel(raw, out, None, "k", style_detect=False, prepare=False,
                               avoid_peak=False, log=lambda *_: None)
        finally:
            dt.translate_chapter = original
        assert calls == ["第2章"], calls
        assert titles(out) == ["Truyện", "Chương 1: Ten 1", "Chương 2: Moi", "Chương 3: Ten 3"], titles(out)
    print("PASS dich (che do thuong) tu sua truoc khi dich")


def test_volume_restart_only_dedup():
    with tempfile.TemporaryDirectory() as d:
        raw, out = os.path.join(d, "raw.txt"), os.path.join(d, "raw.txt.viet.txt")
        write(raw, [raw_ch(1), raw_ch(2), ("第1章", ["卷二a", "卷二b"]), ("第1章", ["卷二a", "卷二b"])])
        assert dt.heal_novel(raw, out, log=lambda *_: None)
        assert titles(raw) == ["TRUYỆN", "第1章", "第2章", "第1章"], titles(raw)
        assert parse_chapters(raw)[3]["paragraphs"] == ["卷二a", "卷二b"]
    print("PASS quyen danh so lai: chi bo ban trung that, khong sap xep")


def test_mismatched_translation_not_touched():
    with tempfile.TemporaryDirectory() as d:
        raw, out = os.path.join(d, "raw.txt"), os.path.join(d, "raw.txt.viet.txt")
        write(raw, [raw_ch(1), raw_ch(3), raw_ch(2)])
        write(out, [tr_ch(1), ("Chương 2", [f"x{i}" for i in range(20)])], head="Truyện", head_sep=True)
        before = open(raw, encoding="utf-8").read(), open(out, encoding="utf-8").read()
        assert not dt.heal_novel(raw, out, log=lambda *_: None)
        assert (open(raw, encoding="utf-8").read(), open(out, encoding="utf-8").read()) == before
    print("PASS file dich lech file tho: khong tu sua, khong dong vao file")


def test_auto_fix_report_and_package_dedupe():
    from crawler import unique_chapters
    from build_epub import package_due
    with tempfile.TemporaryDirectory() as d:
        raw, out = os.path.join(d, "raw.txt"), os.path.join(d, "raw.txt.viet.txt")
        write(raw, [raw_ch(1), raw_ch(3), raw_ch(3), raw_ch(2), raw_ch(4)])
        write(out, [tr_ch(1), tr_ch(3)], head="Truyện", head_sep=True)
        r = dt.auto_fix_novel(raw, out, log=lambda *_: None)
        assert r == {"fixed": True, "total": 4, "translated": 1, "stashed": 1, "todo": 2}, r
        assert not dt.auto_fix_novel(raw, out, log=lambda *_: None)["fixed"]
    chs = [{"title": "a", "paragraphs": ["x"]}, {"title": "a", "paragraphs": ["x"]},
           {"title": "a", "paragraphs": ["y"]}]
    assert len(unique_chapters(chs)) == 2
    assert package_due(25) and not package_due(24)
    print("PASS nut tu sua doi chieu + dong goi bo chuong trung + dong goi theo dot")


if __name__ == "__main__":
    test_auto_fix_report_and_package_dedupe()
    test_heal_duplicates_and_order_then_translate_only_missing()
    test_stream_uses_stash()
    test_translate_novel_heals_by_itself()
    test_volume_restart_only_dedup()
    test_mismatched_translation_not_touched()
