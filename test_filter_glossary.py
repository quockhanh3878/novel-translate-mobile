import sys

from deepseek_translate import (
    select_glossary_for_chapter,
    find_idioms_in_chapter,
    build_terms_block,
    clean_idioms,
    merge_idioms,
    split_idiom_terms,
    clean_new_terms,
    merge_new_terms,
    check_term_usage,
    cleanup_glossary_meta,
    _parse_sse_stream,
)


CHAPTER = {
    "title": "第20章　有苦難言",
    "paragraphs": ["顧從軍看了看上官嫣紅，杯水車薪，毫無辦法。", "任九貴走了。"],
}


def _check_select_only_terms_in_chapter():
    # Chi gui muc co trong chuong; khop duoc ca khi glossary la gian the, truyen phon the.
    glossary = {"顾从军": "Cố Tòng Quân", "上官嫣红": "Thượng Quan Yên Hồng",
                "上官": "Thượng Quan", "任九贵": "Nhậm Cửu Quý", "李四": "Lý Tứ"}
    selected = select_glossary_for_chapter(glossary, CHAPTER)
    assert list(selected) == ["顾从军", "上官嫣红", "上官", "任九贵"], selected


def _check_select_huge_glossary_capped():
    glossary = {f"词{i:03d}": f"tu {i}" for i in range(1000)}
    chapter = {"title": "", "paragraphs": ["".join(glossary)]}
    assert len(select_glossary_for_chapter(glossary, chapter, max_entries=50)) == 50


def _check_idiom_hints():
    known, fresh = find_idioms_in_chapter(CHAPTER)
    assert "杯水车薪" in fresh and not known, (known, fresh)
    # Nghia "nghĩa đen: ..." cua tu dien chung khong duoc gui (day model dich sat chu).
    assert "nghĩa đen" not in fresh["杯水车薪"] and "(thành ngữ)" not in fresh["杯水车薪"], fresh
    # Thanh ngu da co trong glossary thi khong goi y lai.
    assert "杯水车薪" not in find_idioms_in_chapter(CHAPTER, skip={"杯水车薪": "muối bỏ bể"})[1]


def _check_idiom_memory_hints():
    chapter = {"title": "", "paragraphs": ["杯水車薪，瞎子做拉麪，狗急跳牆，哭笑不得。"]}
    memory = {"杯水车薪": {"vi": "muối bỏ bể", "variants": {"muối bỏ bể": 2}},  # da dung that
              "瞎子做拉面": {"vi": "thằng mù kéo mì, nói nhảm",           # cau dai, tu dien chung khong co
                          "variants": {"thằng mù kéo mì, nói nhảm": 1}},
              "不以为然": {"vi": "không cho là đúng", "source": "dich_truoc"},  # dich truoc, chua duyet
              "哭笑不得": {"vi": "", "freq": 49}}              # moi quet, chua co cach dich
    chapter["paragraphs"][0] += "他不以為然。"
    known, fresh = find_idioms_in_chapter(chapter, memory=memory)
    assert known["杯水车薪"] == "muối bỏ bể", known
    assert known["瞎子做拉面"] == "thằng mù kéo mì, nói nhảm", known
    assert known["狗急跳墙"] == "Chó cùng rứt giậu", known       # danh sach anh Ber tuyen tay
    assert "哭笑不得" in fresh, fresh
    # Ban dich truoc chua duyet chi la nghia tham khao, khong ep dung lai.
    assert "不以为然" not in known and fresh["不以为然"] == "nghĩa: không cho là đúng", (known, fresh)
    assert list(known) == ["杯水车薪", "瞎子做拉面", "狗急跳墙"], "phai theo thu tu xuat hien"
    memory["不以为然"]["approved"] = True
    assert find_idioms_in_chapter(chapter, memory=memory)[0]["不以为然"] == "không cho là đúng"
    # Muc da duyet thang danh sach tuyen tay.
    memory["狗急跳墙"] = {"vi": "tức nước vỡ bờ", "approved": True}
    assert find_idioms_in_chapter(chapter, memory=memory)[0]["狗急跳墙"] == "tức nước vỡ bờ"
    block = build_terms_block({}, known, fresh)
    assert "杯水车薪 = muối bỏ bể" in block and "哭笑不得" in block, block


def _check_clean_idioms():
    raw = {"杯水車薪": "muối bỏ bể",            # co trong ban dich -> giu (khoa ve gian the)
           "狗急跳牆": "chó cùng rứt giậu",      # khong co trong chuong -> bo
           "任九貴": "không có trong bản dịch",  # model khai nhung ban dich khong dung -> bo
           "毫無辦法": "nghĩa đen: không cách"}  # nghia den -> bo
    paragraphs = ["Cố Tòng Quân nhìn Thượng Quan, đúng là Muối bỏ bể."]
    assert clean_idioms(raw, CHAPTER, paragraphs) == {"杯水车薪": "muối bỏ bể"}


def _check_merge_idioms():
    memory = {"杯水车薪": {"vi": "", "freq": 3, "source": "truyen"}}
    assert merge_idioms(memory, {"杯水车薪": "muối bỏ biển"}, 1) == ["杯水车薪"]
    merge_idioms(memory, {"杯水车薪": "muối bỏ bể"}, 2)
    assert memory["杯水车薪"]["vi"] == "muối bỏ biển", "hoa thi giu cach dich cu"
    merge_idioms(memory, {"杯水车薪": "muối bỏ bể"}, 3)
    e = memory["杯水车薪"]
    assert e["vi"] == "muối bỏ bể" and e["chapters"] == 3 and e["first"] == 1 and e["last"] == 3, e
    # Muc da duyet khong bao gio bi doi.
    memory["狗急跳墙"] = {"vi": "chó cùng rứt giậu", "approved": True}
    for i in range(3):
        merge_idioms(memory, {"狗急跳墙": "tức nước vỡ bờ"}, 10 + i)
    assert memory["狗急跳墙"]["vi"] == "chó cùng rứt giậu"


def _check_split_idiom_terms():
    # Thanh ngu bi nhet vao new_terms (一丘之貉 tu tu dien nhan dien, 狗急跳墙 tu danh sach tuyen,
    # 瞎子做拉面 tu tu dien rieng) phai tach sang idioms; ten rieng giu nguyen.
    terms, idioms = split_idiom_terms(
        {"任九貴": "Nhậm Cửu Quý", "一丘之貉": "cá mè một lứa", "狗急跳墙": "chó cùng rứt giậu",
         "瞎子做拉面": "kéo nhăng kéo cuội"},
        {"瞎子做拉面": {"vi": ""}})
    assert terms == {"任九貴": "Nhậm Cửu Quý"}, terms
    assert set(idioms) == {"一丘之貉", "狗急跳墙", "瞎子做拉面"}, idioms


def _check_novel_paths():
    # Glossary va tu dien thanh ngu rieng cua truyen nam canh file dich.
    assert glossary_path_for("a/truyen_raw.txt.viet.txt") == "a/truyen_raw.txt.viet_glossary.json"
    assert idioms_path_for("a/truyen_raw.txt.viet.txt") == "a/truyen_raw.txt.viet_idioms.json"


def _check_clean_new_terms():
    raw = {"任九貴": "Nhậm Cửu Quý", "王五": "Vương Ngũ", "毫無": "không có 毫",
           "abc": "x", "顧從軍": ""}
    assert clean_new_terms(raw, CHAPTER) == {"任九貴": "Nhậm Cửu Quý"}
    # Glossary chi nhan ten rieng (co chu viet hoa): tu thuong model tu them bi bo.
    ch = {"title": "", "paragraphs": ["劉茜發了朋友圈，被拘禁在水上人家酒店。"]}
    raw = {"劉茜": "Lưu Thiến", "朋友圈": "danh bạ", "拘禁": "giam giữ", "發了": "Phát",
           "水上人家酒店": "khách sạn Thủy Thượng Nhân Gia"}
    assert clean_new_terms(raw, ch) == {"劉茜": "Lưu Thiến",
                                        "水上人家酒店": "khách sạn Thủy Thượng Nhân Gia"}


def _check_merge_never_overwrites():
    glossary = {"顾从军": "Cố Tòng Quân"}
    added = merge_new_terms(glossary, {"顧從軍": "Cố Tùng Quân", "任九貴": "Nhậm Cửu Quý"})
    assert added == {"任九貴": "Nhậm Cửu Quý"}, added
    assert glossary["顾从军"] == "Cố Tòng Quân" and "顧從軍" not in glossary


def _check_term_usage():
    terms = {"上官嫣红": "Thượng Quan Yên Hồng", "上官": "Thượng Quan", "顾从军": "Cố Tòng Quân"}
    ok = ["Cố Tòng Quân nhìn Thượng Quan Yên Hồng."]
    assert check_term_usage(CHAPTER, ok, terms) == []
    bad = ["Cố Tùng Quân nhìn Thượng Quan Yên Hồng."]
    assert check_term_usage(CHAPTER, bad, terms) == [("顾从军", "Cố Tòng Quân")]


def _check_cleanup_keeps_glossary():
    # Chi don meta; glossary khong bi dong toi (ten nhan vat phai giu mai).
    meta = {
        "a": {"last_seen": 5, "count": 1},    # idle -> xoa meta
        "b": {"last_seen": 200, "count": 1},  # gan day -> giu
        "c": {"last_seen": 5, "count": 3},    # idle nhung count>1 -> giu
    }
    new_meta, removed = cleanup_glossary_meta(meta, current_chapter=200)
    assert removed == ["a"], removed
    assert "a" not in new_meta and "b" in new_meta and "c" in new_meta


class _FakeResp:
    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)


def _check_sse_usage():
    lines = [
        'data: {"choices":[{"delta":{"content":"xin"}}]}',
        'data: {"choices":[{"delta":{"content":" chao"}}],"usage":{"prompt_tokens":12,"completion_tokens":6,"total_tokens":18}}',
        "data: [DONE]",
    ]
    content, usage = _parse_sse_stream(_FakeResp(lines))
    assert content == "xin chao", content
    assert usage == {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18}, usage


def main():
    _check_select_only_terms_in_chapter()
    _check_select_huge_glossary_capped()
    _check_idiom_hints()
    _check_idiom_memory_hints()
    _check_clean_idioms()
    _check_merge_idioms()
    _check_split_idiom_terms()
    _check_clean_new_terms()
    _check_merge_never_overwrites()
    _check_term_usage()
    _check_cleanup_keeps_glossary()
    _check_sse_usage()
    print("OK: glossary theo chuong/tu dien thanh ngu/merge/check/cleanup/sse-usage hoat dong dung.")


if __name__ == "__main__":
    main()
