"""Kiem tra gio cao diem DeepSeek: thu 2-6, 9-12h va 14-18h gio Bac Kinh, tru ngay le
Trung Quoc (docs: "excluding Chinese public holidays", ngay le va cuoi tuan la gia thap).

Chay: .venv\\Scripts\\python test_peak_hours.py
"""

from datetime import datetime

import deepseek_translate as dt


def bj(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=dt.BEIJING_TZ)


def demo():
    # Ngay thuong, trong khung cao diem -> cao diem
    assert dt.is_peak_hour(bj(2026, 10, 8, 10)) is True      # thu 5, ngay lam viec thuong
    assert dt.is_peak_hour(bj(2026, 9, 30, 15)) is True      # thu 4, truoc ky nghi quoc khanh
    assert dt.is_peak_hour(bj(2026, 10, 8, 9)) is True       # dau khung 9h
    assert dt.is_peak_hour(bj(2026, 10, 8, 17, 59)) is True  # cuoi khung 14-18h

    # Ngoai khung gio -> khong cao diem
    assert dt.is_peak_hour(bj(2026, 10, 8, 12)) is False     # het khung sang
    assert dt.is_peak_hour(bj(2026, 10, 8, 13)) is False
    assert dt.is_peak_hour(bj(2026, 10, 8, 18)) is False
    assert dt.is_peak_hour(bj(2026, 10, 8, 8, 59)) is False

    # Ngay le Trung Quoc (thu 2-6 nhung nghi) -> khong cao diem
    assert dt.is_peak_hour(bj(2026, 10, 1, 10)) is False     # quoc khanh
    assert dt.is_peak_hour(bj(2026, 10, 5, 15)) is False     # nghi bu
    assert dt.is_peak_hour(bj(2026, 10, 7, 10)) is False     # nghi dieu chinh (lam bu 10/10)
    assert dt.is_peak_hour(bj(2026, 2, 18, 10)) is False     # tet nguyen dan
    assert dt.is_peak_hour(bj(2027, 2, 8, 15)) is False      # tet 2027 (du lieu nam sau)

    # Cuoi tuan (ke ca ngay thu 7 phai di lam bu) -> khong cao diem (docs: chi thu 2-6)
    assert dt.is_peak_hour(bj(2026, 10, 10, 10)) is False
    assert dt.is_peak_hour(bj(2026, 10, 11, 15)) is False

    # Doi mui gio: gio VN (UTC+7) 11:00 = 12:00 Bac Kinh -> het cao diem; 10:00 VN van cao diem
    from datetime import timedelta, timezone
    vn = timezone(timedelta(hours=7))
    assert dt.is_peak_hour(datetime(2026, 10, 8, 10, 0, tzinfo=vn)) is True
    assert dt.is_peak_hour(datetime(2026, 10, 8, 11, 0, tzinfo=vn)) is False

    # Khong co thu vien ngay le -> than trong: coi la ngay thuong (cho thua, khong ton them tien)
    saved = dt._china_public_holidays
    try:
        dt._china_public_holidays = lambda year: frozenset()
        assert dt.is_peak_hour(bj(2026, 10, 1, 10)) is True
        assert dt.is_peak_hour(bj(2026, 10, 10, 10)) is False  # cuoi tuan van khong cao diem
    finally:
        dt._china_public_holidays = saved

    print("OK: gio cao diem tinh dung thu 2-6, 9-12h/14-18h Bac Kinh, tru ngay le Trung Quoc.")


def demo_stream_waits():
    """Che do stream phai cho het gio cao diem truoc moi chuong (tru khi --allow-peak),
    giong translate_novel; dung giua luc cho thi khong dich chuong nao."""
    import os
    import tempfile

    chapters = [{"title": f"c{i}", "paragraphs": ["x"]} for i in (1, 2)]
    translated_titles = []
    waits = []

    def fake_translate(chapter, *args, chapter_idx=None, **kwargs):
        translated_titles.append(chapter["title"])
        return {"title": f"Chuong {chapter_idx}", "paragraphs": ["y"], "new_terms": {},
                "idioms": {}, "term_warnings": [], "usage": {}}

    saved_translate, saved_wait = dt.translate_chapter, dt.wait_until_offpeak
    dt.translate_chapter = fake_translate
    try:
        for avoid, stop_waiting, expect_waits, expect_translated in [
            (True, False, 2, 2),    # cho truoc moi chuong, het cao diem thi dich tiep
            (False, False, 0, 2),   # --allow-peak: khong cho
            (True, True, 1, 0),     # bi dung giua luc cho: khong dich gi
        ]:
            waits.clear()
            translated_titles.clear()
            dt.wait_until_offpeak = lambda log=print, should_stop=None, poll_seconds=30, _s=stop_waiting: (
                waits.append(1) or _s)
            with tempfile.TemporaryDirectory() as directory:
                out = os.path.join(directory, "out.txt")
                dt.translate_novel_stream(iter(chapters), out, os.path.join(directory, "g.json"),
                                          "fake-key", avoid_peak=avoid, log=lambda m: None)
            assert len(waits) == expect_waits, (avoid, stop_waiting, waits)
            assert len(translated_titles) == expect_translated, (avoid, stop_waiting, translated_titles)
    finally:
        dt.translate_chapter, dt.wait_until_offpeak = saved_translate, saved_wait

    print("OK: stream cho het gio cao diem truoc moi chuong, --allow-peak bo qua, dung duoc luc cho.")


if __name__ == "__main__":
    demo()
    demo_stream_waits()
