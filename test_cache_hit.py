import deepseek_translate as dt

def main():
    print("Testing if TRANSLATE_SYSTEM_PROMPT contains glossary placeholder...")
    has_glossary = "{glossary_block}" in dt.TRANSLATE_SYSTEM_PROMPT
    print(f"Has glossary block: {has_glossary}")
    
    chapter = {"title": "Test Title", "paragraphs": ["This is paragraph 1", "This is paragraph 2"]}
    user_prompt = dt.build_user_prompt(chapter)
    
    print("\nUser Prompt output:")
    print(user_prompt)
    
    if "Glossary" in user_prompt:
        print("\n[FAILED] User prompt still contains Glossary!")
    else:
        print("\n[PASSED] User prompt does not contain Glossary.")
        
    print("\nTesting build_system_prompt logic...")
    glossary = {"Test": "Kiem tra", "Apple": "Qua tao", "Zebra": "Ngua van"}
    glossary_lines = "\n".join(f"{zh} = {vi}" for zh, vi in glossary.items())
    glossary_block = f"Glossary (Trung = Viet, dung co dinh):\n{glossary_lines or '(khong co)'}\n"
    
    system_prompt = dt.TRANSLATE_SYSTEM_PROMPT.format(
        style_guide_block="",
        term_categories="các thuật ngữ",
        glossary_block=glossary_block
    )
    
    if "Test = Kiem tra\nApple = Qua tao\nZebra = Ngua van" in system_prompt:
        print("\n[PASSED] System prompt contains glossary in correct insertion order!")
    else:
        print("\n[FAILED] System prompt glossary is missing or order is incorrect!")

    # Kiem tra co lap cache giua 2 truyen cung thu muc va theo noi dung nguon
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        out_a = os.path.join(d, "truyen_a.viet.txt")
        out_b = os.path.join(d, "truyen_b.viet.txt")
        ch_a = {"title": "第1章", "paragraphs": ["Nội dung truyện A."]}
        ch_b = {"title": "第1章", "paragraphs": ["Nội dung truyện B."]}
        dt._save_cache(out_a, 1, {"title": "Chương 1", "paragraphs": ["Bản dịch A."]}, ch_a)
        assert dt._load_cache(out_a, 1, ch_a)["paragraphs"] == ["Bản dịch A."]
        assert dt._load_cache(out_b, 1, ch_b) is None, "Truyen B khong duoc doc nham cache cua truyen A"
        assert dt._load_cache(out_a, 1, ch_b) is None, "Noi dung nguon thay doi phai bo qua cache cu"
        print("[PASSED] Write-ahead cache isolated per novel and source content.")

if __name__ == "__main__":
    main()
