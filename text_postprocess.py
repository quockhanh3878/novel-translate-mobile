"""
text_postprocess.py - Hậu xử lý dùng chung cho văn bản tiếng Việt dịch ra từ MarianMT và LLMs.
"""

from __future__ import annotations

import re

# Bộ chữ cái tiếng Việt đầy đủ (bao gồm mọi dấu thanh: ngang, huyền, sắc, hỏi, ngã, nặng)
_VOWELS_LOWER = "àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
_VOWELS_UPPER = _VOWELS_LOWER.upper()

_LOWER_CLASS = "a-z" + _VOWELS_LOWER
_UPPER_CLASS = "A-Z" + _VOWELS_UPPER

# Ngoặc kép: cả kiểu thẳng (") lẫn kiểu cong Anh-Mỹ (“ ”) và cong đơn (' ').
_OPEN_QUOTES = "“‘\""
_CLOSE_QUOTES = "”’\""
_ANY_QUOTE = _OPEN_QUOTES + _CLOSE_QUOTES

_REPEAT_RUN_RE = re.compile(r"(?iu)\b(\w+)(?:[ \t]+\1\b){2,}")


def _collapse_repeated_words(text: str) -> str:
    """Gộp các từ lặp liên tục >=3 lần thành 1 từ (dấu hiệu decode bị quẩn)."""
    return _REPEAT_RUN_RE.sub(lambda m: m.group(1), text)


# Lỗi model rất hay gặp: thay vì đặt lời thoại trong ngoặc kép ngay từ đầu,
# model đặt phần chú thích người nói ra cuối câu kèm đúng 1 dấu ngoặc kép lẻ.
_STRAY_QUOTE_SPLIT_RE = re.compile(rf"^(.*\S)\s*[{_ANY_QUOTE}]\s*([^{_ANY_QUOTE}]*)$")


def _fix_stray_trailing_quote(text: str) -> str:
    quote_chars = set(_OPEN_QUOTES + _CLOSE_QUOTES)
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
        return head
    return f"“{head}” {tail}"


def _fix_missing_opening_quote(text: str) -> str:
    """Nếu dấu ngoặc kép đầu tiên trong câu là dấu đóng, có thể câu bị khuyết dấu mở ở đầu."""
    first_quote_idx = -1
    first_quote_char = ''
    for i, char in enumerate(text):
        if char in _ANY_QUOTE:
            first_quote_idx = i
            first_quote_char = char
            break
            
    if first_quote_idx != -1 and first_quote_char in _CLOSE_QUOTES:
        if first_quote_char == '”':
            return '“' + text
        elif first_quote_char == '’':
            return '‘' + text
        elif first_quote_char == '"':
            return '"' + text
    return text


def postprocess(text: str) -> str:
    """
    Hậu xử lý toàn diện: sửa lỗi dấu câu, khoảng trắng, viết hoa tiếng Việt,
    và dọn các cụm từ bị lặp do lỗi decode.
    """
    text = re.sub(r"[ \t]+", " ", text)
    text = _collapse_repeated_words(text)
    text = re.sub(r"^[\s,;.\-!?]+", "", text)
    text = _fix_missing_opening_quote(text)
    text = _fix_stray_trailing_quote(text)
    text = re.sub(r"\s+([,;.!?])", r"\1", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    text = re.sub(r"\.,", ".", text)
    text = re.sub(r",\.", ".", text)
    text = re.sub(r"\.\?", "?", text)
    text = re.sub(r"\.\!", "!", text)
    text = re.sub(r",!", "!", text)
    text = re.sub(r",\?", "?", text)
    text = re.sub(r";,", ";", text)

    # Khoảng trắng thừa quanh ngoặc kép
    text = re.sub(rf"([{_OPEN_QUOTES}])\s+", r"\1", text)
    text = re.sub(rf"\s+([{_CLOSE_QUOTES}])", r"\1", text)

    text = re.sub(rf"([.!?])([{_UPPER_CLASS}])", r"\1 \2", text)
    text = re.sub(rf",([^\s\"'\)\]0-9{_CLOSE_QUOTES}])", r", \1", text)

    if text:
        text = text[0].upper() + text[1:]

    def cap_after_punct(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()

    text = re.sub(rf"([.!?]\s+)([{_LOWER_CLASS}])", cap_after_punct, text)

    def cap_after_quote(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()

    text = re.sub(rf"([{_OPEN_QUOTES}])\s*([{_LOWER_CLASS}])", cap_after_quote, text)

    # Dọn lại lần nữa
    text = re.sub(rf"([{_OPEN_QUOTES}])\s+", r"\1", text)
    text = re.sub(rf"\s+([{_CLOSE_QUOTES}])", r"\1", text)

    text = re.sub(r"\.\.\.\.+", "...", text)
    text = re.sub(r"[,;]\s*$", ".", text)
    text = re.sub(r":\s*$", ".", text)
    return text.strip()


def postprocess_title(title: str) -> str:
    """Hau xu ly cho ten chuong: giu ngan gon, chi don sach dau xuong & khoang trang thua."""
    title = title.strip()
    # Xoa dau cau o dau/cuoi (neu AI dich them)
    title = re.sub(r"^[\s,;.\-!?]+", "", title)
    title = re.sub(r"[,;.\-!?]+\s*$", "", title)
    # Gop khoang trang thua
    title = re.sub(r"\s+", " ", title)
    return title.strip()
