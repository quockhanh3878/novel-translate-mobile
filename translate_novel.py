import sys
import os
import time
import re
from pathlib import Path

# Add current dir to path to import app.py
sys.path.append(str(Path(__file__).resolve().parent))

try:
    from app import translate
    from opencc import OpenCC
except Exception as e:
    print(f"Error importing dependencies: {e}")
    sys.exit(1)

try:
    from app import translate
    from opencc import OpenCC
except Exception as e:
    print(f"Error importing dependencies: {e}")
    sys.exit(1)

from text_postprocess import postprocess

# Initialize Traditional to Simplified converter
cc = OpenCC('t2s')

# Default glossary for "Disan Chongrenge" (The Third Personality)
DEFAULT_GLOSSARY = {
    "王八喜": "Vương Bát Hỉ",
    "任九贵": "Nhậm Cửu Quý",
    "尹白鸽": "Doãn Bạch Cát",
    "纪震": "Kỷ Chấn",
    "谢远航": "Tạ Viễn Hàng",
    "华登峰": "Hoa Đăng Phong",
    "牛再山": "Ngưu Tái Sơn",
    "牛松": "Ngưu Tùng",
    "上官": "Thượng Quan",
    "上官顺敏": "Thượng Quan Thuận Mẫn",
    "常书欣": "Thường Thư Hân"
}

# Standard placeholders for name restoration
ZH_PLACEHOLDERS = ['张三', '李四', '王五', '赵六', '钱七', '孙八']
VI_PLACEHOLDERS = ['Trương Tam', 'Lý Tứ', 'Vương Ngũ', 'Triệu Lục', 'Tiền Thất', 'Tôn Bát']


def parse_novel(input_file):
    chapters = []
    current_chapter = None
    
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        title_match = re.match(r"^===\s*(第\d+章.*?|Chapter.*?|TRUYỆN.*?)\s*===$", line_str)
        if title_match:
            if current_chapter:
                chapters.append(current_chapter)
            current_chapter = {
                "title": title_match.group(1).strip(),
                "paragraphs": []
            }
        else:
            if line_str == "========================================":
                continue
            if current_chapter:
                current_chapter["paragraphs"].append(line.strip())
                
    if current_chapter:
        chapters.append(current_chapter)
        
    return chapters


def get_translated_chapters(output_file):
    if not os.path.exists(output_file):
        return set()
        
    translated = set()
    with open(output_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    matches = re.findall(r"^===\s*(.*?)\s*===$", content, re.MULTILINE)
    for m in matches:
        translated.add(m.strip())
    return translated


def translate_clause(clause, glossary=None):
    clause_stripped = clause.strip()
    if not clause_stripped or re.fullmatch(r'[\s\W]+', clause_stripped):
        return ''
        
    active_replacements = []
    temp_clause = clause_stripped
    
    if glossary:
        sorted_keys = sorted(glossary.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in temp_clause:
                idx = len(active_replacements)
                if idx < len(ZH_PLACEHOLDERS):
                    placeholder = ZH_PLACEHOLDERS[idx]
                    target_name = glossary[key]
                    temp_clause = temp_clause.replace(key, placeholder)
                    active_replacements.append((VI_PLACEHOLDERS[idx], target_name))
                    
    simplified = cc.convert(temp_clause)
    translated_text, _, _ = translate(simplified)
    
    for placeholder_vi, real_name in active_replacements:
        translated_text = re.sub(re.escape(placeholder_vi), real_name, translated_text, flags=re.IGNORECASE)
        
    return translated_text


def translate_paragraph(para, glossary=None):
    if not para.strip():
        return ''
        
    if re.fullmatch(r'[…\.\!\?\,\;\:\s，。！？；：、「」""''《》〈〉\u2026]+', para):
        return para
        
    # app.translate() đã tự chia câu dài bằng chunker CNN theo token (xem
    # split_text_by_token_limit trong app.py), chọn điểm cắt hợp lý về ngữ nghĩa
    # thay vì cắt cứng. Trước đây hàm này tự chia lại theo dấu câu ở mọi đoạn
    # > 40 ký tự và dịch từng mệnh đề tách rời, mất ngữ cảnh giữa các mệnh đề
    # -> câu dịch rời rạc, sai trật tự từ. Giờ giao thẳng cả đoạn cho
    # app.translate() xử lý để giữ ngữ cảnh tối đa.
    raw = translate_clause(para, glossary)
    return postprocess(raw) if raw else ''


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    input_file = "truyen_de_tam_trung_nhan_cach.txt"
    output_file = "truyen_de_tam_trung_nhan_cach_viet.txt"
    
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} not found. Please run the crawler first.")
        return

    print("Parsing input novel file...")
    chapters = parse_novel(input_file)
    print(f"Parsed {len(chapters)} chapters from {input_file}.")
    
    translated_titles = get_translated_chapters(output_file)
    print(f"Detected {len(translated_titles)} already translated chapters.")
    
    with open(output_file, "a", encoding="utf-8") as f_out:
        for idx, ch in enumerate(chapters, 1):
            expected_title = f"Chương {idx}"
            if expected_title in translated_titles or "TRUYỆN" in title:
                print(f"[{idx}/{len(chapters)}] Skipping: {title} (already translated)")
                continue
                
            print(f"[{idx}/{len(chapters)}] Translating: {title}...")
            translated_title = expected_title
            
            f_out.write(f"=== {translated_title} ===\n\n")
            
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=3) as executor:
                results = list(executor.map(lambda p: translate_paragraph(p, DEFAULT_GLOSSARY), ch["paragraphs"]))
            
            for translated_para in results:
                if translated_para:
                    f_out.write(f"{translated_para}\n\n")
                
            f_out.write("\n" + "="*40 + "\n\n")
            f_out.flush()
            
            print(f"[{idx}/{len(chapters)}] Completed: {title} -> {translated_title}")
            
    print("Translation completed successfully!")

if __name__ == "__main__":
    main()
