"""Kiem tra buoc chuan bi (prepare_novel.py) voi call_deepseek gia lap - khong ton phi API."""
import json
import os
import random
import tempfile

import build_idiom_dictionary
import prepare_novel
from deepseek_translate import find_idioms_in_chapter, load_glossary, load_idiom_memory
from prepare_novel import find_name_candidates, prepare_novel as run_prepare, state_path_for

NAMES = {"任九贵": "Nhậm Cửu Quý", "华登峰": "Hoa Đăng Phong", "邓燕": "Đặng Yến", "岚海市": "thành phố Lam Hải",
         "董魁强": "Đổng Khôi Cường"}
PREFIX = ["", "这时", "后来", "只见", "于是", "但是", "忽然", "那天"]
VERB = ["看着", "笑道", "问", "走进", "拿起", "想起", "点头", "摇头", "离开", "放下"]
OBJ = ["门口", "电话", "桌子", "窗外", "文件", "汽车", "茶杯", "楼梯", "报纸", "钥匙"]
FILLER = ["天色渐渐暗了", "外面下着小雨", "谁也没有说话", "屋里很安静", "街上的人不多",
          "他叹了口气", "远处传来汽笛声", "风吹得很冷"]


def _chapters(names, count=40, seed=1, idioms=True):
    rnd = random.Random(seed)
    chapters = []
    for i in range(count):
        paras = []
        for _ in range(10):
            name = rnd.choice(names)
            paras.append(f"{rnd.choice(PREFIX)}{name}{rnd.choice(VERB)}{rnd.choice(OBJ)}，{rnd.choice(FILLER)}。")
        if idioms and i % 5 == 0:
            paras.append("大家哭笑不得，这点钱杯水车薪。")
        chapters.append({"title": f"第{i + 1}章", "paragraphs": paras})
    return chapters


def _check_find_name_candidates():
    names = ["任九贵", "华登峰", "邓燕", "岚海市"]
    cands = find_name_candidates(_chapters(names))
    found = {c["zh"] for c in cands}
    for name in names:
        assert name in found, (name, sorted(found))
    for c in cands:
        zh = c["zh"]
        assert zh not in ("哭笑不得", "杯水车薪"), "thanh ngu khong phai ung vien ten"
        assert not any(zh != n and n in zh and len(zh) - len(n) == 1 for n in names), \
            f"ten dinh 1 chu (VD 任九贵问) phai bi loai: {zh}"
        assert c["example"] and zh in c["example"], c


class _FakeApi:
    def __init__(self):
        self.calls = []

    def __call__(self, system_prompt, user_prompt, *args, **kwargs):
        self.calls.append((system_prompt, user_prompt, kwargs.get("reasoning_effort")))
        if "TÊN RIÊNG" in system_prompt:
            rows = user_prompt.split("câu trích:\n", 1)[1].splitlines()
            keys = [r.split(" | ")[0] for r in rows]
            # Tu thuong model tra ve (chu thuong) phai bi loc, chi giu ten that.
            return {"names": {k: {"vi": NAMES.get(k, "cái cửa"), "loai": "nguoi"} for k in keys}}
        rows = user_prompt.split("câu trích:\n", 1)[1].splitlines()
        return {"idioms": {r.split(" | ")[0]: f"cách dịch {i}" for i, r in enumerate(rows)}}


def _check_prepare_novel():
    fake = _FakeApi()
    old = prepare_novel.call_deepseek, build_idiom_dictionary.call_deepseek
    prepare_novel.call_deepseek = build_idiom_dictionary.call_deepseek = fake
    try:
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "truyen.viet.txt")
            gpath, ipath = os.path.join(d, "truyen.viet_glossary.json"), os.path.join(d, "truyen.viet_idioms.json")
            json.dump({"邓燕": "Đặng Yến"}, open(gpath, "w", encoding="utf-8"), ensure_ascii=False)
            json.dump({"哭笑不得": {"vi": "dở khóc dở cười", "approved": True},
                       "杯水车薪": {"vi": "một cốc nước", "source": "dich_truoc"}},
                      open(ipath, "w", encoding="utf-8"), ensure_ascii=False)
            chapters = _chapters(["任九贵", "华登峰", "邓燕", "岚海市"])
            summary = run_prepare(chapters, out, None, "k", log=lambda m: None)

            glossary = load_glossary(gpath)
            assert glossary["邓燕"] == "Đặng Yến", "ten da co khong bi ghi de"
            for name in ("任九贵", "华登峰", "岚海市"):
                assert glossary[name] == NAMES[name], glossary
            assert all(vi != "cái cửa" for vi in glossary.values()), "tu thuong khong vao glossary"
            name_calls = [c for c in fake.calls if "TÊN RIÊNG" in c[0]]
            assert name_calls and all(c[2] == "high" for c in fake.calls), "buoc chuan bi dung suy luan cao"
            assert "邓燕 = Đặng Yến" in name_calls[0][1] and "邓燕 |" not in name_calls[0][1], \
                "ten da co chi dua vao 'Ten da chot', khong xet lai"

            memory = load_idiom_memory(ipath)
            assert memory["哭笑不得"]["vi"] == "dở khóc dở cười" and memory["哭笑不得"]["approved"]
            assert memory["杯水车薪"]["source"] == "chuan_bi" and memory["杯水车薪"]["vi"].startswith("cách dịch")
            assert summary["idioms_added"] == 1, summary

            # Thanh ngu tu buoc chuan bi chi la goi y (khong ep dung lai), muc da duyet van ep.
            known, fresh = find_idioms_in_chapter(chapters[0], memory=memory)
            assert known["哭笑不得"] == "dở khóc dở cười", known
            assert fresh["杯水车薪"] == "gợi ý: " + memory["杯水车薪"]["vi"], fresh

            state = json.load(open(state_path_for(out), encoding="utf-8"))
            assert state["done"] and state["chapters"] == 40 and "任九贵" in state["names_checked"], state

            # Chay lai, truyen khong doi -> khong goi API.
            fake.calls.clear()
            assert run_prepare(chapters, out, None, "k", log=lambda m: None)["skipped"] and not fake.calls

            # Cao them chuong co nhan vat moi -> chi xet ung vien moi, khong dich lai thanh ngu.
            more = chapters + _chapters(["董魁强"], count=6, seed=2, idioms=False)
            run_prepare(more, out, None, "k", log=lambda m: None)
            sent = "\n".join(c[1] for c in fake.calls)
            assert fake.calls and all("TÊN RIÊNG" in c[0] for c in fake.calls), "khong co thanh ngu moi"
            assert "董魁强 |" in sent and "任九贵 |" not in sent, sent
            assert load_glossary(gpath)["董魁强"] == "Đổng Khôi Cường"
    finally:
        prepare_novel.call_deepseek, build_idiom_dictionary.call_deepseek = old


def _check_translate_novel_runs_prepare():
    """translate_novel goi buoc chuan bi truoc: chuong 1 da co ten chot san trong prompt.
    Buoc chuan bi loi (VD mat mang) thi van dich binh thuong."""
    import deepseek_translate as t

    chapters = _chapters(["任九贵", "华登峰", "邓燕", "岚海市"], count=12)
    raw_text = "".join(f"=== {ch['title']} ===\n\n" + "\n\n".join(ch["paragraphs"]) + "\n\n" + "=" * 40 + "\n\n"
                       for ch in chapters)
    prompts = []

    def fake_chapter(system_prompt, user_prompt, *args, **kwargs):
        prompts.append(system_prompt)
        n = len(json.loads(user_prompt.split("\n", 1)[1])["paragraphs"])
        return {"title": "Chương", "paragraphs": ["Đoạn dịch."] * n, "new_terms": {}, "idioms": {}}

    def broken(*args, **kwargs):
        raise RuntimeError("mat mang")

    old = t.call_deepseek, prepare_novel.call_deepseek, build_idiom_dictionary.call_deepseek
    try:
        for api, expect_names in ((_FakeApi(), True), (broken, False)):
            t.call_deepseek = fake_chapter
            prepare_novel.call_deepseek = build_idiom_dictionary.call_deepseek = api
            prompts.clear()
            with tempfile.TemporaryDirectory() as d:
                raw, out = os.path.join(d, "raw.txt"), os.path.join(d, "vi.txt")
                open(raw, "w", encoding="utf-8").write(raw_text)
                failed = t.translate_novel(raw, out, None, "k", style_detect=False, avoid_peak=False,
                                           log=lambda m: None)
                assert not failed and t.count_chapters(out) == 12, failed
                first = prompts[0]
                has = any(f"{zh} = {vi}" in first for zh, vi in NAMES.items())
                assert has == expect_names, first[-400:]
                assert expect_names or "(khong co)" in first, first[-400:]
    finally:
        t.call_deepseek, prepare_novel.call_deepseek, build_idiom_dictionary.call_deepseek = old


if __name__ == "__main__":
    _check_find_name_candidates()
    _check_prepare_novel()
    _check_translate_novel_runs_prepare()
    print("OK: buoc chuan bi lap glossary ten + thanh ngu dung, chay lai chi xet phan moi.")
