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

if __name__ == "__main__":
    main()
