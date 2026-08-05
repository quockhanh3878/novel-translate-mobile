"""
test_repetition_penalty.py - Kiem tra get_next_token_id() trong app.py phat lom
theo so lan token da lap, khong phai phat co dinh 1 lan (nguyen nhan gay vong lap
kieu "mot mot X mot mot Y..." o model nho khi decode greedy).

Chay: .venv\\Scripts\\python test_repetition_penalty.py
"""

import numpy as np

from app import DECODER_START_ID, get_next_token_id


def demo():
    vocab_size = 10
    target = 3

    logits = np.zeros(vocab_size, dtype=np.float32)
    logits[target] = 5.0

    # Token lap 1 lan: vua bi phat, van con lon hon cac ung vien khac (0.0).
    generated_once = [DECODER_START_ID, target]
    picked = get_next_token_id(logits, generated_once, penalty=1.6, ngram_size=0, min_new_tokens=0)
    assert picked == target, f"expected {target} to still win after 1 repeat, got {picked}"

    # Token lap nhieu lan lien tiep: phat luy thua phai day no xuong duoi cac ung vien khac.
    generated_many = [DECODER_START_ID] + [target] * 8
    logits2 = logits.copy()
    logits2[7] = 1.0  # ung vien khac, thap hon target ban dau nhung chua bi phat
    picked2 = get_next_token_id(logits2, generated_many, penalty=1.6, ngram_size=0, min_new_tokens=0)
    assert picked2 != target, "escalating penalty phai day token lap lieu vao xuong duoi sau nhieu lan lap"
    assert picked2 == 7, f"expected fallback candidate 7 to win, got {picked2}"

    print("OK: repetition penalty leo thang theo so lan lap dung nhu ky vong.")


if __name__ == "__main__":
    demo()
