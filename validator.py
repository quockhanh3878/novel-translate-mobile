import re
from crawler import parse_chapters

def validate_translation(raw_file: str, translated_file: str, log=print) -> list[dict]:
    log("=== Bat dau Validation (Sanity Check) ===")
    
    try:
        raw_chapters = parse_chapters(raw_file)
    except Exception as e:
        log(f"Loi doc file raw: {e}")
        return [{"type": "error", "message": f"Khong the doc {raw_file}"}]
        
    try:
        trans_chapters = parse_chapters(translated_file)
    except Exception as e:
        log(f"Loi doc file dich: {e}")
        return [{"type": "error", "message": f"Khong the doc {translated_file}"}]
        
    warnings = []
    
    # 1. Kiem tra so luong chuong
    if len(raw_chapters) != len(trans_chapters):
        msg = f"CANH BAO: So chuong khong khop (Raw: {len(raw_chapters)} chuong, Dich: {len(trans_chapters)} chuong)"
        log(msg)
        warnings.append({"type": "warning", "message": msg})
        
    # 2. Kiem tra noi dung tung chuong
    chinese_char_pattern = re.compile(r'[\u4e00-\u9fff]')
    
    for i, ch in enumerate(trans_chapters):
        idx = i + 1
        paras = ch.get("paragraphs", [])
        
        # 2.1 Chuong rong
        if not paras or all(not p.strip() for p in paras):
            msg = f"CANH BAO: Chuong {idx} ({ch.get('title')}) bi rong noi dung."
            log(msg)
            warnings.append({"type": "warning", "chapter": idx, "message": msg})
            continue
            
        # 2.2 Ton du tieng Han
        full_text = "\n".join(paras)
        matches = chinese_char_pattern.findall(full_text)
        if len(matches) > 10:  # Cho phep du mot so it ky tu
            msg = f"CANH BAO: Chuong {idx} ({ch.get('title')}) ton du {len(matches)} ky tu tieng Han. Nghi ngo LLM bo sot hoac khong dich."
            log(msg)
            warnings.append({"type": "warning", "chapter": idx, "message": msg})
            
    if not warnings:
        log("Validation PASSED! Khong phat hien loi nghiem trong nao.")
    else:
        log(f"=== Validation hoan tat voi {len(warnings)} canh bao. ===")
        
    return warnings

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Su dung: python validator.py <raw_file> <translated_file>")
        sys.exit(1)
    validate_translation(sys.argv[1], sys.argv[2])
