"""
post_fix.py – Áp dụng hàm postprocess() lên file dịch đã có sẵn
mà KHÔNG cần chạy lại mô hình MarianMT.

Sử dụng:
    .venv\\Scripts\\python post_fix.py
"""

import sys

from text_postprocess import postprocess


def process_file(input_path: str, output_path: str):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed_lines = []
    for line in lines:
        raw = line.rstrip('\r\n')
        # Don't touch separator lines or chapter headers
        if raw.startswith('===') or raw == '=' * 40 or raw.strip() == '':
            fixed_lines.append(line)
            continue
        # Apply postprocess
        fixed = postprocess(raw)
        fixed_lines.append(fixed + '\n')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

    print(f"Done. Fixed file saved to: {output_path}")


if __name__ == '__main__':
    src = 'truyen_de_tam_trung_nhan_cach_viet.txt'
    dst = 'truyen_de_tam_trung_nhan_cach_viet_fixed.txt'
    process_file(src, dst)
