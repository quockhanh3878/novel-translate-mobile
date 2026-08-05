"""
test_stray_quote_fix.py - Kiem tra _fix_stray_trailing_quote() trong text_postprocess.py
xu ly dung loi model hay gap: dat chu thich nguoi noi (vd "Bat Hi Dao.") ra cuoi
cau kem 1 dau ngoac kep le, thay vi bao quanh loi thoai bang ngoac kep.

Chay: .venv\\Scripts\\python test_stray_quote_fix.py
"""

from text_postprocess import postprocess


def demo():
    # Dau ngoac le o cuoi + chu thich nguoi noi -> bao quanh phan loi thoai, giu chu thich.
    out = postprocess(
        "Đối với ngươi, nữ nhân như y phục, trên đỉnh cao nhất cũng chỉ tính quần lót. “Bát Hỉ Đạo."
    )
    assert out == "“Đối với ngươi, nữ nhân như y phục, trên đỉnh cao nhất cũng chỉ tính quần lót.” Bát Hỉ Đạo.", out

    # Dau ngoac le nhung phan duoi chi la rac dau cau -> bo dau ngoac, giu nguyen cau.
    out = postprocess("Đâu phải chúng ta. “.")
    assert out == "Đâu phải chúng ta.", out

    # Da co dung 1 cap ngoac kep (2 ky tu) -> khong dong den, tranh doan sai.
    out = postprocess("Bát Hỉ nói: “Không sao đâu, mọi thứ đều ổn.”")
    assert out == "Bát Hỉ nói: “Không sao đâu, mọi thứ đều ổn.”", out

    print("OK: dau ngoac kep le cuoi cau duoc ghep lai dung nhu ky vong.")


if __name__ == "__main__":
    demo()
