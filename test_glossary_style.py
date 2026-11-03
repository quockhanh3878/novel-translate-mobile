"""Ten trung tu thong dung khong bi ep cung; van phong khong doi giua truyen.

Chay: python test_glossary_style.py
"""

import json
import os
import tempfile

import deepseek_translate as dt


def test_ambiguous_names_not_forced():
    terms = {"靜靜": "Tĩnh Tĩnh", "大兵": "Đại Binh", "高文昌": "Cao Văn Xương"}
    forced, ambiguous = dt.split_ambiguous_terms(terms)
    assert forced == {"高文昌": "Cao Văn Xương"}, forced
    assert set(ambiguous) == {"靜靜", "大兵"}, ambiguous

    block = dt.build_terms_block(terms)
    head, tail = block.split("TRÙNG với từ thông dụng")
    assert "高文昌 = Cao Văn Xương" in head and "靜靜" not in head, block
    assert "靜靜 = Tĩnh Tĩnh" in tail and "大兵 = Đại Binh" in tail, block

    # 靜靜地 dich "lặng lẽ" la dung -> khong canh bao; ten ep cung bi bo sot van canh bao
    chapter = {"title": "第1章", "paragraphs": ["高文昌靜靜地等着。"]}
    warnings = dt.check_term_usage(chapter, ["Ông ấy lặng lẽ chờ."], terms)
    assert warnings == [("高文昌", "Cao Văn Xương")], warnings
    print("PASS ten trung tu thong dung chi goi y theo ngu canh, khong ep, khong canh bao sai")


def test_style_not_reevaluated_mid_novel():
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        out = os.path.join(d, "raw.txt.viet.txt")
        with open(raw, "w", encoding="utf-8") as f:
            f.write("=== TRUYỆN ===\n\n")
            for i in range(1, 251):
                f.write(f"=== 第{i}章 ===\n\n原文{i}\n\n{dt.CHAPTER_SEP}")
        style_file = out.rsplit(".", 1)[0] + "_style.txt"
        with open(style_file, "w", encoding="utf-8") as f:
            json.dump({"style_guide": "giong co", "term_categories": "x"}, f)

        detect_calls, prompts = [], set()
        orig_detect, orig_translate = dt.detect_style_guide, dt.translate_chapter
        dt.detect_style_guide = lambda *a, **k: (detect_calls.append(1), {"style_guide": "giong moi"})[1]

        def fake_translate(chapter, system_prompt, *a, chapter_idx=None, **k):
            prompts.add(system_prompt)
            return {"title": "", "paragraphs": ["Viet"], "new_terms": {}, "idioms": {},
                    "term_warnings": [], "usage": {}}

        dt.translate_chapter = fake_translate
        try:
            dt.translate_novel(raw, out, None, "k", prepare=False, avoid_peak=False, log=lambda *_: None)
        finally:
            dt.detect_style_guide, dt.translate_chapter = orig_detect, orig_translate
        assert detect_calls == [] and len(prompts) == 1, (detect_calls, len(prompts))
        with open(style_file, encoding="utf-8") as f:
            assert json.load(f)["style_guide"] == "giong co"
    print("PASS van phong chot 1 lan cho ca truyen, 250 chuong dung chung 1 system prompt")


if __name__ == "__main__":
    test_ambiguous_names_not_forced()
    test_style_not_reevaluated_mid_novel()
