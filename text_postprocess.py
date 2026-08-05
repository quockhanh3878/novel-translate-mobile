"""
text_postprocess.py - Hậu xử lý dùng chung cho văn bản tiếng Việt dịch ra từ MarianMT.

Trước đây hàm postprocess() bị copy trùng lặp giữa translate_novel.py và post_fix.py,
khiến 2 bản dễ lệch nhau khi sửa lỗi. File này gộp lại thành 1 nguồn duy nhất, đồng thời
vá 2 lỗi thực tế phát hiện được khi soát lại bản dịch đã sinh ra:

1. Các regex xử lý khoảng trắng quanh dấu ngoặc kép ("\\s+', '\\s+"') và regex viết hoa
   sau ngoặc kép chỉ nhắm vào dấu " thẳng, KHÔNG khớp với dấu ngoặc kép cong “ ” mà model
   thực tế sinh ra. Hệ quả: câu thoại kiểu `“ Bát Hỉ, ...` bị thừa khoảng trắng sau dấu mở
   ngoặc, và chữ cái đầu câu thoại không được viết hoa (`“ ta cửu quý` thay vì `“Ta cửu quý`).
2. Danh sách nguyên âm có dấu dùng trong các regex viết hoa sau dấu câu chỉ có dấu huyền/sắc/
   ngã cơ bản, THIẾU hoàn toàn dấu hỏi, dấu nặng và các nguyên âm ư/ơ/â/ă kết hợp dấu
   (ví dụ ả, ậ, ử, ợ...). Nghĩa là rất nhiều từ tiếng Việt bắt đầu bằng các âm này không được
   viết hoa sau dấu chấm/ngoặc kép. Đã bổ sung đầy đủ bộ chữ cái tiếng Việt.

Ngoài ra bổ sung một bước dọn dẹp mới: gộp các từ bị lặp liên tiếp 3 lần trở lên
(ví dụ "một một một một một..." lặp hàng chục lần) - đây là dấu hiệu decode bị lặp/quẩn
của mô hình nhỏ khi decode kiểu greedy, quan sát được thực tế trong
truyen_de_tam_trung_nhan_cach_viet.txt. Chỉ gộp khi lặp >=3 lần để không đụng vào các từ
láy hợp lệ trong tiếng Việt (vốn thường chỉ lặp đúng 2 lần, ví dụ "từ từ", "vội vội").
"""

from __future__ import annotations

import re

# Bộ chữ cái tiếng Việt đầy đủ (bao gồm mọi dấu thanh: ngang, huyền, sắc, hỏi, ngã, nặng)
# — bản gốc trong translate_novel.py/post_fix.py chỉ có huyền/sắc/ngã nên bỏ sót rất nhiều từ.
_VOWELS_LOWER = "àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
_VOWELS_UPPER = _VOWELS_LOWER.upper()

_LOWER_CLASS = "a-z" + _VOWELS_LOWER
_UPPER_CLASS = "A-Z" + _VOWELS_UPPER

# Ngoặc kép: cả kiểu thẳng (") lẫn kiểu cong Anh-Mỹ (“ ”) và cong đơn (' ').
# Model dịch thực tế xuất ra ngoặc kép cong, nhưng bản gốc chỉ xử lý ngoặc thẳng.
_OPEN_QUOTES = "“‘\""
_CLOSE_QUOTES = "”’\""
_ANY_QUOTE = _OPEN_QUOTES + _CLOSE_QUOTES

_REPEAT_RUN_RE = re.compile(r"(?iu)\b(\w+)(?:[ \t]+\1\b){2,}")


def _collapse_repeated_words(text: str) -> str:
    """Gộp các từ lặp liên tục >=3 lần thành 1 từ (dấu hiệu decode bị quẩn)."""
    return _REPEAT_RUN_RE.sub(lambda m: m.group(1), text)


# Lỗi model rất hay gặp (~8% số dòng trong bản dịch thực tế): thay vì đặt lời thoại
# trong ngoặc kép ngay từ đầu (dạng "X nói: “...”" hoặc "“...” X nói."), model đặt
# phần chú thích người nói (vd "Bát Hỉ Đạo.") ra cuối câu kèm đúng 1 dấu ngoặc kép lẻ,
# không có dấu đóng/mở tương ứng. Ví dụ thực tế:
#   "Đối với ngươi, nữ nhân như y phục, trên đỉnh cao nhất cũng chỉ tính quần lót. “Bát Hỉ Đạo."
# Sửa bằng cách đóng ngoặc kép lại quanh phần lời thoại, giữ phần chú thích ở cuối
# (đúng dạng "..." X nói. mà C1.txt cũng dùng phổ biến).
_STRAY_QUOTE_SPLIT_RE = re.compile(rf"^(.*\S)\s*[{_ANY_QUOTE}]\s*([^{_ANY_QUOTE}]*)$")


def _fix_stray_trailing_quote(text: str) -> str:
    quote_chars = set(_OPEN_QUOTES + _CLOSE_QUOTES)
    # Chỉ xử lý khi CẢ DÒNG có đúng 1 ký tự ngoặc kép: đây là tín hiệu an toàn cho biết
    # nó thực sự bị lẻ cặp. Dòng có 2+ ngoặc kép thường là hội thoại đã đúng cấu trúc,
    # tự ý đoán lại dễ sai nên bỏ qua.
    if sum(text.count(q) for q in quote_chars) != 1:
        return text
    m = _STRAY_QUOTE_SPLIT_RE.match(text)
    if not m:
        return text
    head = m.group(1).strip()
    tail = m.group(2).strip()
    if not head:
        return text
    if not tail or not tail.strip(" \t.,;:!?"):
        # Đuôi chỉ còn dấu câu rác chứ không phải tên người nói -> bỏ luôn ngoặc lẻ.
        return head
    # Dùng ngoặc kép cong (không phải ngoặc thẳng "") vì các regex dọn khoảng trắng
    # quanh ngoặc kép phía dưới coi " vừa là mở vừa là đóng -> sẽ nuốt nhầm khoảng
    # trắng cần giữ giữa ngoặc đóng và phần chú thích người nói.
    return f"“{head}” {tail}"


def postprocess(text: str) -> str:
    """
    Hậu xử lý toàn diện: sửa lỗi dấu câu, khoảng trắng, viết hoa tiếng Việt,
    và dọn các cụm từ bị lặp do lỗi decode.
    """
    text = re.sub(r"[ \t]+", " ", text)
    text = _collapse_repeated_words(text)
    text = re.sub(rf"^[\s,;.\-!?{_ANY_QUOTE}\']+", "", text)
    # Phải chạy SAU bước xoá ngoặc kép/rác ở đầu dòng phía trên, vì hàm này có thể tự
    # chèn thêm 1 dấu ngoặc mở ở đầu câu — chèn trước thì bị chính bước xoá rác ăn mất.
    text = _fix_stray_trailing_quote(text)
    text = re.sub(r"\s+([,;.!?])", r"\1", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"\.{2,}(?!\.)", ".", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    text = re.sub(r"\.,", ".", text)
    text = re.sub(r",\.", ".", text)
    text = re.sub(r"\.\?", "?", text)
    text = re.sub(r"\.\!", "!", text)
    text = re.sub(r",!", "!", text)
    text = re.sub(r",\?", "?", text)
    text = re.sub(r";,", ";", text)

    # Khoảng trắng thừa quanh ngoặc kép — áp dụng cho mọi kiểu ngoặc, không chỉ ngoặc thẳng.
    text = re.sub(rf"([{_OPEN_QUOTES}])\s+", r"\1", text)
    text = re.sub(rf"\s+([{_CLOSE_QUOTES}])", r"\1", text)

    text = re.sub(rf"([.!?])([{_UPPER_CLASS}])", r"\1 \2", text)
    # Không chèn khoảng trắng nếu ký tự theo sau là ngoặc kép đóng (mọi kiểu) —
    # trước đây chỉ loại trừ ngoặc thẳng nên vẫn chèn nhầm khoảng trắng giữa
    # dấu phẩy và ngoặc kép cong đóng, ví dụ "cách," + "”" -> "cách, ”" sai.
    text = re.sub(rf",([^\s\"'\)\]0-9{_CLOSE_QUOTES}])", r", \1", text)

    if text:
        text = text[0].upper() + text[1:]

    def cap_after_punct(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()

    text = re.sub(rf"([.!?]\s+)([{_LOWER_CLASS}])", cap_after_punct, text)

    def cap_after_quote(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()

    text = re.sub(rf"([{_OPEN_QUOTES}])\s*([{_LOWER_CLASS}])", cap_after_quote, text)

    # Dọn lại lần nữa phòng trường hợp các bước phía trên vô tình chèn thêm
    # khoảng trắng quanh ngoặc kép (idempotent, không ảnh hưởng nếu đã sạch).
    text = re.sub(rf"([{_OPEN_QUOTES}])\s+", r"\1", text)
    text = re.sub(rf"\s+([{_CLOSE_QUOTES}])", r"\1", text)

    text = re.sub(r"\.\.\.\.+", "...", text)
    text = re.sub(r"[,;]\s*$", ".", text)
    text = re.sub(r":\s*$", ".", text)
    return text.strip()
