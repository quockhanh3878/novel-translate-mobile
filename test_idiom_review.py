"""Kiem tra build_idiom_dictionary.apply_review: ap ket qua trang duyet thanh ngu."""
import json
import os
import tempfile

from build_idiom_dictionary import apply_review, scan_novel


def _check_apply_review():
    with tempfile.TemporaryDirectory() as d:
        curated_path = os.path.join(d, "curated.json")
        json.dump({"以牙还牙": "Gậy ông đập lưng ông", "刻舟求剑": "Khắc thuyền tìm kiếm",
                   "狗急跳墙": "Chó cùng rứt giậu"},
                  open(curated_path, "w", encoding="utf-8"), ensure_ascii=False)
        memory = {"小心翼翼": {"vi": "rón rén cẩn thận", "source": "dich_truoc", "freq": 45},
                  "近水楼台": {"vi": "cận thủy lâu đài", "source": "dich_truoc", "freq": 5}}
        decisions = {"items": {
            "a": {"zh": "以牙还牙", "vi": "ăn miếng trả miếng", "status": "approved", "src": "tuyen"},
            "b": {"zh": "刻舟求劍", "vi": "", "status": "rejected", "src": "tuyen"},   # phon the van khop
            "c": {"zh": "小心翼翼", "vi": "cẩn thận từng li từng tí", "status": "approved", "src": "dich"},
            "d": {"zh": "近水楼台", "vi": "cận thủy lâu đài", "status": "rejected", "src": "dich"},
            "e": {"zh": "狗急跳墙", "vi": "x", "status": "", "src": "tuyen"},             # hoan tac -> bo qua
        }}
        stats = apply_review(decisions, memory, curated_path)
        curated = json.load(open(curated_path, encoding="utf-8"))
        assert curated == {"以牙还牙": "ăn miếng trả miếng", "狗急跳墙": "Chó cùng rứt giậu"}, curated
        assert memory["小心翼翼"]["vi"] == "cẩn thận từng li từng tí" and memory["小心翼翼"]["approved"]
        assert memory["近水楼台"]["vi"] == "" and not memory["近水楼台"]["approved"]
        assert stats == {"tuyen_approved": 1, "tuyen_rejected": 1, "dich_approved": 1, "dich_rejected": 1}, stats


def _check_scan_novel():
    chapters = [{"title": "", "paragraphs": ["他哭笑不得。", "又是哭笑不得。"]},
                {"title": "", "paragraphs": ["哭笑不得，狗急跳牆了。"]}]
    counts, examples = scan_novel(chapters)
    assert counts["哭笑不得"] == 2, counts          # dem theo so chuong, khong theo so lan
    assert counts["狗急跳墙"] == 1 and "狗急跳墙" in examples["狗急跳墙"], (counts, examples)


if __name__ == "__main__":
    _check_apply_review()
    _check_scan_novel()
    print("OK: quet truyen va ap ket qua duyet thanh ngu dung.")
