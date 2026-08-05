#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import math
import os
import time
import traceback
import unicodedata
from collections import Counter, OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import numpy as np
import onnxruntime as ort

# Thư mục model mặc định là thư mục chứa chính app.py.
# Có thể override: MODEL_DIR=/path/to/model python app.py
APP_DIR = Path(__file__).resolve().parent
default_model_dir = APP_DIR / "model" if (APP_DIR / "model").is_dir() else APP_DIR
MODEL_DIR = Path(os.environ.get("MODEL_DIR", str(default_model_dir))).expanduser().resolve()


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else None


def _is_bad_translation_onnx(path: Path) -> bool:
    low = path.name.lower()
    return any(x in low for x in ("chunk", "boundary", "split", "segment"))


def _iter_files(root: Path, patterns: list[str], recursive: bool = False) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(root.rglob(pattern) if recursive else root.glob(pattern))
    # unique + file only
    uniq: dict[str, Path] = {}
    for f in found:
        if f.is_file():
            uniq[str(f.resolve())] = f.resolve()
    return list(uniq.values())


def _ranked_find(
    root: Path,
    patterns: list[str],
    *,
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    recursive: bool = False,
) -> Path | None:
    candidates = _iter_files(root, patterns, recursive=recursive)
    scored: list[tuple[int, str, Path]] = []
    for f in candidates:
        low = f.name.lower()
        full = str(f).lower()
        if include and not all(x in full for x in include):
            continue
        if exclude and any(x in full for x in exclude):
            continue
        score = 0
        # Ưu tiên file nằm ngay cùng thư mục app/model hơn file trong subfolder.
        if f.parent == root:
            score -= 100
        # Ưu tiên tên ngắn/chuẩn hơn.
        score += len(f.name)
        scored.append((score, f.name.lower(), f))
    if not scored:
        return None
    scored.sort()
    return scored[0][2]


def _find_required(name: str, env_name: str, patterns: list[str], *, exclude: tuple[str, ...] = ()) -> Path:
    env = _env_path(env_name)
    if env is not None:
        return env
    found = _ranked_find(MODEL_DIR, patterns, exclude=exclude, recursive=False)
    if found is None:
        # fallback: quét subfolder một tầng/nhiều tầng khi người dùng để model trong thư mục con
        found = _ranked_find(MODEL_DIR, patterns, exclude=exclude, recursive=True)
    if found is None:
        raise FileNotFoundError(f"Không tìm thấy {name} trong {MODEL_DIR}. Có thể set {env_name}=...")
    return found


ENCODER_PATH = _find_required(
    "encoder ONNX",
    "ENCODER_PATH",
    ["encoder*.onnx", "*encoder*.onnx"],
    exclude=("chunk", "boundary", "split", "segment", "decoder"),
)
DECODER_PATH = _find_required(
    "decoder ONNX",
    "DECODER_PATH",
    ["decoder_model.onnx", "decoder*.onnx", "*decoder*.onnx"],
    exclude=("with_past", "past", "merged", "chunk", "boundary", "split", "segment", "encoder"),
)
DECODER_WITH_PAST_PATH = _env_path("DECODER_WITH_PAST_PATH") or _ranked_find(
    MODEL_DIR,
    ["decoder_with_past*.onnx", "*with_past*.onnx", "*past*.onnx"],
    exclude=("merged", "chunk", "boundary", "split", "segment", "encoder"),
    recursive=True,
) or (MODEL_DIR / "decoder_with_past_model.onnx")
DECODER_MERGED_PATH = _env_path("DECODER_MERGED_PATH") or _ranked_find(
    MODEL_DIR,
    ["decoder_model_merged.onnx", "*merged*.onnx"],
    exclude=("chunk", "boundary", "split", "segment", "encoder"),
    recursive=True,
) or (MODEL_DIR / "decoder_model_merged.onnx")
TOKENIZER_PATH = _find_required("tokenizer.json", "TOKENIZER_PATH", ["tokenizer.json", "*tokenizer*.json"], exclude=("chunk", "boundary", "split", "segment"))
CONFIG_PATH = _find_required("config.json", "CONFIG_PATH", ["config.json", "*config*.json"], exclude=("chunk", "boundary", "split", "segment"))
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "7860"))
REQUESTED_MAX_SOURCE_LENGTH = int(os.environ.get("MAX_SOURCE_LENGTH", "128"))
# Model ONNX này có positional/add tensor cố định 128. Nếu ép 256/512 sẽ lỗi broadcast 128 by 512.
# Có thể override nếu bạn export lại model hỗ trợ dài hơn: MODEL_MAX_SOURCE_LENGTH=256/512.
MODEL_MAX_SOURCE_LENGTH = int(os.environ.get("MODEL_MAX_SOURCE_LENGTH", "128"))
MAX_SOURCE_LENGTH = min(REQUESTED_MAX_SOURCE_LENGTH, MODEL_MAX_SOURCE_LENGTH)
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "127"))
# Mặc định KHÔNG chia chunk, vì chia đoạn có thể làm mất ngữ cảnh và tạo bản dịch kỳ.
# Bật lại nếu muốn: CHUNK_LONG_INPUT=1 python app.py
CHUNK_LONG_INPUT = os.environ.get("CHUNK_LONG_INPUT", "1").strip().lower() in {"1", "true", "on", "yes"}
# Model chia chunk TinyCNN. Layout mặc định:
#   MODEL_DIR/app.py
#   MODEL_DIR/encoder_model.onnx, decoder_model.onnx, tokenizer.json, config.json
#   MODEL_DIR/cat_dong/chunk_boundary_cnn.onnx
#   MODEL_DIR/cat_dong/chunk_char_vocab.json
#   MODEL_DIR/cat_dong/chunk_boundary_config.json
# Có thể override riêng nếu muốn:
#   CHUNKER_DIR=/path/to/chunker
#   CHUNKER_ONNX_PATH=/path/to/chunker.onnx
#   CHUNKER_VOCAB_PATH=/path/to/vocab.json
#   CHUNKER_CONFIG_PATH=/path/to/config.json
_DEFAULT_CHUNKER_DIR = MODEL_DIR / "cat_dong" if (MODEL_DIR / "cat_dong").is_dir() else MODEL_DIR
CHUNKER_DIR = Path(os.environ.get("CHUNKER_DIR", str(_DEFAULT_CHUNKER_DIR))).expanduser().resolve()
# Mặc định chỉ quét ĐÚNG thư mục chunker. Với layout trên là cat_dong/.
# Không quét ngược về MODEL_DIR để tránh bắt nhầm config.json của model dịch.
# Nếu bạn cố tình để chunker sâu hơn nữa: CHUNKER_RECURSIVE=1 python app.py
CHUNKER_RECURSIVE = os.environ.get("CHUNKER_RECURSIVE", "0").strip().lower() in {"1", "true", "on", "yes"}
CHUNKER_ONNX_PATH = _env_path("CHUNKER_ONNX_PATH") or _ranked_find(
    CHUNKER_DIR,
    ["*chunk*.onnx", "*boundary*.onnx", "*split*.onnx", "*segment*.onnx"],
    exclude=("encoder", "decoder", "with_past", "merged"),
    recursive=CHUNKER_RECURSIVE,
) or (CHUNKER_DIR / "chunk_boundary_cnn.onnx")
CHUNKER_VOCAB_PATH = _env_path("CHUNKER_VOCAB_PATH") or _ranked_find(
    CHUNKER_DIR,
    ["*chunk*vocab*.json", "*char*vocab*.json", "*boundary*vocab*.json", "*vocab*.json"],
    exclude=("tokenizer", "sentencepiece", "spm", "config"),
    recursive=CHUNKER_RECURSIVE,
) or (CHUNKER_DIR / "chunk_char_vocab.json")
CHUNKER_CONFIG_PATH = _env_path("CHUNKER_CONFIG_PATH") or _ranked_find(
    CHUNKER_DIR,
    # Không dùng "*config*.json" chung chung vì sẽ bắt nhầm config.json của model dịch.
    ["*chunk*config*.json", "*boundary*config*.json", "*split*config*.json", "*segment*config*.json"],
    exclude=("tokenizer", "model",),
    recursive=CHUNKER_RECURSIVE,
) or (CHUNKER_DIR / "chunk_boundary_config.json")
USE_CHUNKER = os.environ.get("USE_CHUNKER", "1").strip().lower() in {"1", "true", "on", "yes"}
CHUNKER_MIN_FILL_RATIO = float(os.environ.get("CHUNKER_MIN_FILL_RATIO", "0.55"))
CHUNKER_THRESHOLD = os.environ.get("CHUNKER_THRESHOLD", "").strip()
# Khi không chia chunk, input dài hơn khả năng encoder sẽ báo lỗi rõ thay vì cắt âm thầm.
# Nếu muốn cắt thẳng đoạn đầu: STRICT_SOURCE_LIMIT=0 python app.py
STRICT_SOURCE_LIMIT = os.environ.get("STRICT_SOURCE_LIMIT", "1").strip().lower() not in {"0", "false", "off", "no"}
THREADS = int(os.environ.get("ORT_THREADS", str(max(1, min(4, os.cpu_count() or 1)))))
PROVIDER_MODE = os.environ.get("ORT_PROVIDER", "xnnpack").strip().lower()
# auto: ưu tiên two-decoder cache, bỏ merged vì một số export Optimum bị lỗi broadcast trên Android.
# merged: ép thử decoder_model_merged.onnx. off: tắt cache.
CACHE_MODE = os.environ.get("ORT_CACHE", "auto").strip().lower()

# --- Tham số chất lượng decoding (áp dụng cho mọi chế độ cache, xem get_next_token_id) ---
# Phạt token đã sinh để giảm lặp từ. Giá trị càng cao càng "ép" mô hình chọn từ khác.
REPETITION_PENALTY = float(os.environ.get("REPETITION_PENALTY", "1.6"))
# Chặn tái sinh cụm n-gram đã xuất hiện (mặc định chặn lặp cụm 3 token liên tiếp).
# Đây là nguyên nhân phổ biến khiến câu dịch bị lặp/quẩn khi decode kiểu greedy trên model nhỏ.
# Đặt 0 để tắt.
NO_REPEAT_NGRAM_SIZE = int(os.environ.get("NO_REPEAT_NGRAM_SIZE", "3"))
# Số token tối thiểu phải sinh trước khi cho phép EOS, tránh câu dịch bị cắt cụt quá sớm
# (đặc biệt hay gặp với câu nguồn dài hoặc nhiều mệnh đề).
MIN_NEW_TOKENS = int(os.environ.get("MIN_NEW_TOKENS", "1"))

for path in (CONFIG_PATH, TOKENIZER_PATH, ENCODER_PATH, DECODER_PATH):
    if not path.is_file():
        raise FileNotFoundError(f"Thiếu file: {path}")


def bytes_to_unicode() -> dict[int, str]:
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {b: chr(c) for b, c in zip(bs, cs)}


BYTE_ENCODER = bytes_to_unicode()
BYTE_DECODER = {v: k for k, v in BYTE_ENCODER.items()}


def is_letter(ch: str) -> bool:
    return unicodedata.category(ch).startswith("L")


def is_number(ch: str) -> bool:
    return unicodedata.category(ch).startswith("N")


def is_punct(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return not is_letter(ch) and not is_number(ch) and not ch.isspace() and not cat.startswith("C")


def pretokenize(text: str) -> list[str]:
    if not text:
        return []
    pieces: list[str] = []
    i = 0
    contractions = ("'s", "'t", "'re", "'ve", "'m", "'ll", "'d", "’s", "’t", "’re", "’ve", "’m", "’ll", "’d")
    while i < len(text):
        matched = next((c for c in contractions if text.startswith(c, i)), None)
        if matched:
            pieces.append(matched)
            i += len(matched)
            continue
        ch = text[i]
        if ch.isspace():
            start = i
            while i < len(text) and text[i].isspace():
                i += 1
            spaces = text[start:i]
            if spaces == " " and i < len(text) and not text[i].isspace():
                if is_letter(text[i]):
                    start = i
                    while i < len(text) and is_letter(text[i]):
                        i += 1
                    pieces.append(" " + text[start:i])
                    continue
                if is_number(text[i]):
                    start = i
                    while i < len(text) and is_number(text[i]):
                        i += 1
                    pieces.append(" " + text[start:i])
                    continue
                if is_punct(text[i]):
                    start = i
                    while i < len(text) and is_punct(text[i]):
                        i += 1
                    pieces.append(" " + text[start:i])
                    continue
            pieces.append(spaces)
            continue
        if is_letter(ch):
            start = i
            while i < len(text) and is_letter(text[i]):
                i += 1
            pieces.append(text[start:i])
            continue
        if is_number(ch):
            start = i
            while i < len(text) and is_number(text[i]):
                i += 1
            pieces.append(text[start:i])
            continue
        if is_punct(ch):
            start = i
            while i < len(text) and is_punct(text[i]):
                i += 1
            pieces.append(text[start:i])
            continue
        pieces.append(ch)
        i += 1
    return pieces


class ByteLevelBPETokenizer:
    def __init__(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        model = data.get("model") or {}
        if model.get("type") != "BPE":
            raise RuntimeError(f"Tokenizer không phải BPE: {model.get('type')}")
        if (data.get("pre_tokenizer") or {}).get("type") != "ByteLevel":
            raise RuntimeError("pre_tokenizer không phải ByteLevel")
        vocab = model.get("vocab") or {}
        self.token_to_id = {str(k): int(v) for k, v in vocab.items()}
        self.id_to_token = {v: k for k, v in self.token_to_id.items()}
        self.unk_token = model.get("unk_token")
        self.unk_id = self.token_to_id.get(self.unk_token) if self.unk_token else None
        self.prefix = model.get("continuing_subword_prefix") or ""
        self.suffix = model.get("end_of_word_suffix") or ""
        self.ranks: dict[tuple[str, str], int] = {}
        for rank, merge in enumerate(model.get("merges") or []):
            parts = merge.split() if isinstance(merge, str) else list(merge)
            if len(parts) == 2:
                self.ranks[(str(parts[0]), str(parts[1]))] = rank
        self.added_by_content: dict[str, int] = {}
        self.added_by_id: dict[int, str] = {}
        self.special_ids: set[int] = set()
        for item in data.get("added_tokens") or []:
            try:
                content = str(item["content"])
                token_id = int(item["id"])
            except Exception:
                continue
            self.added_by_content[content] = token_id
            self.added_by_id[token_id] = content
            if item.get("special"):
                self.special_ids.add(token_id)
        pre = data.get("pre_tokenizer") or {}
        dec = data.get("decoder") or {}
        self.add_prefix_space = bool(pre.get("add_prefix_space", False))
        self.decoder_add_prefix_space = bool(dec.get("add_prefix_space", True))
        self.cache: OrderedDict[str, tuple[str, ...]] = OrderedDict()

    @staticmethod
    def pairs(symbols: tuple[str, ...]) -> set[tuple[str, str]]:
        return {(symbols[i], symbols[i + 1]) for i in range(len(symbols) - 1)}

    def bpe(self, token: str) -> tuple[str, ...]:
        if token in self.cache:
            self.cache.move_to_end(token)
            return self.cache[token]
        symbols = tuple(token)
        if len(symbols) < 2:
            return symbols
        while True:
            pairs = self.pairs(symbols)
            if not pairs:
                break
            pair = min(pairs, key=lambda p: self.ranks.get(p, math.inf))
            if pair not in self.ranks:
                break
            first, second = pair
            merged: list[str] = []
            i = 0
            while i < len(symbols):
                try:
                    j = symbols.index(first, i)
                except ValueError:
                    merged.extend(symbols[i:])
                    break
                merged.extend(symbols[i:j])
                i = j
                if i < len(symbols) - 1 and symbols[i] == first and symbols[i + 1] == second:
                    merged.append(first + second)
                    i += 2
                else:
                    merged.append(symbols[i])
                    i += 1
            symbols = tuple(merged)
            if len(symbols) == 1:
                break
        self.cache[token] = symbols
        self.cache.move_to_end(token)
        while len(self.cache) > 50000:
            self.cache.popitem(last=False)
        return symbols

    def encode_piece(self, piece: str) -> list[int]:
        encoded = "".join(BYTE_ENCODER[b] for b in piece.encode("utf-8"))
        pieces = list(self.bpe(encoded))
        if self.prefix:
            pieces = [p if i == 0 else self.prefix + p for i, p in enumerate(pieces)]
        if self.suffix and pieces:
            pieces[-1] += self.suffix
        ids: list[int] = []
        for piece in pieces:
            token_id = self.token_to_id.get(piece, self.unk_id)
            if token_id is None:
                raise RuntimeError(f"Token không có trong vocab: {piece!r}")
            ids.append(token_id)
        return ids

    def encode(self, text: str) -> list[int]:
        if self.add_prefix_space and text and not text.startswith(" "):
            text = " " + text
        result: list[int] = []
        for piece in pretokenize(text):
            result.extend(self.encode_piece(piece))
        return result

    def decode(self, ids: list[int], skip_special_tokens: bool = True) -> str:
        tokens: list[str] = []
        for token_id in ids:
            if skip_special_tokens and token_id in self.special_ids:
                continue
            if token_id in self.added_by_id:
                tokens.append(self.added_by_id[token_id])
                continue
            token = self.id_to_token.get(token_id)
            if token is None:
                continue
            if self.prefix:
                token = token.removeprefix(self.prefix)
            if self.suffix:
                token = token.removesuffix(self.suffix)
            tokens.append(token)
        byte_text = "".join(tokens)
        output = bytearray()
        for ch in byte_text:
            b = BYTE_DECODER.get(ch)
            if b is None:
                output.extend(ch.encode("utf-8", errors="replace"))
            else:
                output.append(b)
        text = output.decode("utf-8", errors="replace")
        if self.decoder_add_prefix_space and text.startswith(" "):
            text = text[1:]
        return text


CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
PAD_ID = int(CONFIG.get("pad_token_id", 25000))
EOS_ID = int(CONFIG.get("eos_token_id", 2))
BOS_ID = int(CONFIG.get("bos_token_id", 1))
DECODER_START_ID = int(CONFIG.get("decoder_start_token_id", PAD_ID))
TOKENIZER = ByteLevelBPETokenizer(TOKENIZER_PATH)


def choose_providers() -> list[str]:
    available = ort.get_available_providers()
    if PROVIDER_MODE == "nnapi":
        preferred = ["NnapiExecutionProvider", "XnnpackExecutionProvider", "CPUExecutionProvider"]
    elif PROVIDER_MODE == "cpu":
        preferred = ["CPUExecutionProvider"]
    else:
        preferred = ["XnnpackExecutionProvider", "CPUExecutionProvider"]
    selected = [p for p in preferred if p in available]
    return selected or ["CPUExecutionProvider"]


PROVIDERS = choose_providers()
OPTIONS = ort.SessionOptions()
OPTIONS.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
OPTIONS.intra_op_num_threads = THREADS
OPTIONS.inter_op_num_threads = 1
OPTIONS.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
ENCODER = ort.InferenceSession(str(ENCODER_PATH), sess_options=OPTIONS, providers=PROVIDERS)
DECODER = ort.InferenceSession(str(DECODER_PATH), sess_options=OPTIONS, providers=PROVIDERS)
DECODER_WITH_PAST = (
    ort.InferenceSession(str(DECODER_WITH_PAST_PATH), sess_options=OPTIONS, providers=PROVIDERS)
    if DECODER_WITH_PAST_PATH.is_file()
    else None
)
DECODER_MERGED = (
    ort.InferenceSession(str(DECODER_MERGED_PATH), sess_options=OPTIONS, providers=PROVIDERS)
    if DECODER_MERGED_PATH.is_file()
    else None
)


def names(session: ort.InferenceSession) -> set[str]:
    return {x.name for x in session.get_inputs()}


def find_name(all_names: set[str] | list[str], exact: list[str], contains: list[str] | None = None) -> str | None:
    name_set = set(all_names)
    for candidate in exact:
        if candidate in name_set:
            return candidate
    if contains:
        for name in all_names:
            lower = name.lower()
            if all(part.lower() in lower for part in contains):
                return name
    return None


ENC_NAMES = names(ENCODER)
DEC_NAMES = names(DECODER)
ENC_INPUT = find_name(ENC_NAMES, ["input_ids", "encoder_input_ids"])
ENC_MASK = find_name(ENC_NAMES, ["attention_mask", "encoder_attention_mask"])
DEC_INPUT = find_name(DEC_NAMES, ["input_ids", "decoder_input_ids", "input_ids.1", "decoder_input_ids.1"], ["input", "ids"])
DEC_HIDDEN = find_name(DEC_NAMES, ["encoder_hidden_states", "encoder_outputs", "encoder_last_hidden_state"], ["encoder", "hidden"])
DEC_MASK = find_name(DEC_NAMES, ["encoder_attention_mask", "attention_mask"], ["encoder", "mask"])
DEC_LOGITS = find_name([x.name for x in DECODER.get_outputs()], ["logits"], ["logit"])
if ENC_INPUT is None or DEC_INPUT is None or DEC_HIDDEN is None:
    raise RuntimeError("Không nhận diện được input/output ONNX")


def ort_dtype(type_name: str) -> np.dtype:
    return np.dtype({
        "tensor(float)": np.float32,
        "tensor(float16)": np.float16,
        "tensor(double)": np.float64,
        "tensor(int64)": np.int64,
        "tensor(int32)": np.int32,
        "tensor(bool)": np.bool_,
    }.get(type_name, np.float32))


def resolve_dim(dim: Any, batch: int, decoder_len: int, encoder_len: int) -> int:
    if isinstance(dim, int) and dim >= 0:
        return dim
    text = str(dim).lower()
    if "batch" in text:
        return batch
    if "encoder" in text and "sequence" in text:
        return encoder_len
    if "sequence" in text:
        return decoder_len
    return 0


def missing_input(meta: Any, batch: int, decoder_len: int, encoder_len: int) -> np.ndarray:
    lower = meta.name.lower()
    if "use_cache_branch" in lower:
        return np.asarray(False, dtype=np.bool_)
    if "cache_position" in lower:
        return np.arange(decoder_len, dtype=np.int64)
    shape = [resolve_dim(dim, batch, decoder_len, encoder_len) for dim in meta.shape]
    return np.zeros(shape, dtype=ort_dtype(meta.type))

class DecoderInfo:
    def __init__(self, session: ort.InferenceSession):
        self.session = session
        self.inputs = list(session.get_inputs())
        self.outputs = list(session.get_outputs())
        self.input_names = [x.name for x in self.inputs]
        self.output_names = [x.name for x in self.outputs]
        self.name_set = set(self.input_names)
        self.input = find_name(
            self.input_names,
            ["input_ids", "decoder_input_ids", "input_ids.1", "decoder_input_ids.1"],
            ["input", "ids"],
        )
        self.hidden = find_name(
            self.input_names,
            ["encoder_hidden_states", "encoder_outputs", "encoder_last_hidden_state"],
            ["encoder", "hidden"],
        )
        self.mask = find_name(
            self.input_names,
            ["encoder_attention_mask", "attention_mask"],
            ["encoder", "mask"],
        )
        self.logits = find_name(self.output_names, ["logits"], ["logit"])
        self.logits_index = self.output_names.index(self.logits) if self.logits in self.output_names else 0
        self.use_cache = find_name(self.input_names, ["use_cache_branch"], ["use", "cache"])
        self.cache_position = find_name(self.input_names, ["cache_position"], ["cache", "position"])
        self.past_inputs = [x for x in self.inputs if self.is_past_name(x.name)]
        self.present_outputs = [
            i for i, x in enumerate(self.outputs)
            if self.is_present_name(x.name) and i != self.logits_index
        ]
        self.cache_pairs = self.make_cache_pairs()
        # decoder_with_past_model.onnx của Optimum thường KHÔNG có encoder_hidden_states.
        # Nó nhận cross-attention cache qua past_key_values.*.encoder.key/value thay vào đó.
        # Vì vậy chỉ bắt buộc hidden khi model không có nhóm encoder cache input.
        self.encoder_past_input_names = [x.name for x in self.past_inputs if ".encoder." in x.name.lower()]
        self.decoder_past_input_names = [x.name for x in self.past_inputs if ".decoder." in x.name.lower()]
        if self.input is None:
            raise RuntimeError("Không nhận diện được input_ids của decoder ONNX")
        if self.hidden is None and not self.encoder_past_input_names:
            raise RuntimeError("Không nhận diện được encoder_hidden_states/cross-attention cache của decoder ONNX")

    @staticmethod
    def is_past_name(name: str) -> bool:
        lower = name.lower()
        return (
            lower.startswith("past_key_values")
            or lower.startswith("past.")
            or lower.startswith("past_")
            or "past_key_values" in lower
        )

    @staticmethod
    def is_present_name(name: str) -> bool:
        lower = name.lower()
        return (
            lower.startswith("present")
            or lower.startswith("present.")
            or lower.startswith("present_")
            or "present_key_values" in lower
        )

    @staticmethod
    def norm_cache_name(name: str) -> str:
        lower = name.lower()
        for old in ("past_key_values", "present_key_values", "present", "past"):
            lower = lower.replace(old, "")
        return lower.replace("/", ".").replace("_", ".")

    def make_cache_pairs(self) -> list[tuple[str, int]]:
        pairs: list[tuple[str, int]] = []
        used_outputs: set[int] = set()
        for past in self.past_inputs:
            candidates = []
            p = past.name
            candidates.append(p.replace("past_key_values", "present"))
            candidates.append(p.replace("past", "present"))
            candidates.append(p.replace("past_key_values", "present_key_values"))
            found = None
            for candidate in candidates:
                if candidate in self.output_names:
                    found = self.output_names.index(candidate)
                    break
            if found is None:
                pn = self.norm_cache_name(past.name)
                for idx in self.present_outputs:
                    if idx not in used_outputs and self.norm_cache_name(self.output_names[idx]) == pn:
                        found = idx
                        break
            if found is not None:
                pairs.append((past.name, found))
                used_outputs.add(found)
        if len(pairs) != len(self.past_inputs) and len(self.past_inputs) == len(self.present_outputs):
            # Fallback theo thứ tự input/output. Optimum thường xuất đúng thứ tự này.
            pairs = [(p.name, o) for p, o in zip(self.past_inputs, self.present_outputs)]
        return pairs

    @property
    def has_present(self) -> bool:
        return bool(self.present_outputs)

    @property
    def can_cache(self) -> bool:
        return bool(self.cache_pairs)


def make_decoder_feeds(
    info: DecoderInfo,
    ids: np.ndarray,
    hidden: np.ndarray,
    mask: np.ndarray,
    *,
    use_cache: bool = False,
    past: dict[str, np.ndarray] | None = None,
    position: int = 0,
) -> dict[str, np.ndarray]:
    feeds: dict[str, np.ndarray] = {info.input: ids}
    if info.hidden:
        feeds[info.hidden] = hidden
    if info.mask:
        feeds[info.mask] = mask
    if info.use_cache:
        feeds[info.use_cache] = np.asarray(bool(use_cache), dtype=np.bool_)
    if info.cache_position:
        if use_cache:
            feeds[info.cache_position] = np.asarray([position], dtype=np.int64)
        else:
            feeds[info.cache_position] = np.arange(ids.shape[1], dtype=np.int64)
    if past:
        feeds.update(past)
    for meta in info.inputs:
        if meta.name not in feeds:
            feeds[meta.name] = missing_input(meta, ids.shape[0], ids.shape[1], mask.shape[1])
    return feeds


def run_decoder_full(info: DecoderInfo, ids: np.ndarray, hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    feeds = make_decoder_feeds(info, ids, hidden, mask, use_cache=False)
    outputs = info.session.run([info.logits], feeds) if info.logits else info.session.run(None, feeds)
    return np.asarray(outputs[0])


def run_decoder_first_present(
    info: DecoderInfo,
    ids: np.ndarray,
    hidden: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    # decoder_model.onnx không có past input, nhưng CÓ output present.* để khởi tạo cache.
    feeds = make_decoder_feeds(info, ids, hidden, mask, use_cache=False, past=None, position=0)
    outputs = info.session.run(None, feeds)
    logits = np.asarray(outputs[info.logits_index])
    present = {
        info.output_names[out_idx]: np.asarray(outputs[out_idx])
        for out_idx in info.present_outputs
        if out_idx < len(outputs)
    }
    return logits, present


def run_decoder_cached(
    info: DecoderInfo,
    ids: np.ndarray,
    hidden: np.ndarray,
    mask: np.ndarray,
    *,
    use_cache: bool,
    past: dict[str, np.ndarray] | None,
    position: int,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    feeds = make_decoder_feeds(
        info,
        ids,
        hidden,
        mask,
        use_cache=use_cache,
        past=past,
        position=position,
    )
    outputs = info.session.run(None, feeds)
    logits = np.asarray(outputs[info.logits_index])
    present = {
        past_name: np.asarray(outputs[out_idx])
        for past_name, out_idx in info.cache_pairs
        if out_idx < len(outputs)
    }
    return logits, present


def safe_decoder_info(name: str, session: ort.InferenceSession | None) -> DecoderInfo | None:
    if session is None:
        return None
    try:
        return DecoderInfo(session)
    except Exception as exc:
        print(f"[WARN] Tắt cache cho {name}: {type(exc).__name__}: {exc}")
        print(f"[WARN] {name} inputs:")
        try:
            for x in session.get_inputs():
                print(f"  - {x.name} | {x.type} | {x.shape}")
            print(f"[WARN] {name} outputs:")
            for x in session.get_outputs():
                print(f"  - {x.name} | {x.type} | {x.shape}")
        except Exception:
            pass
        return None


DECODER_INFO = DecoderInfo(DECODER)
DECODER_WITH_PAST_INFO = safe_decoder_info(DECODER_WITH_PAST_PATH.name, DECODER_WITH_PAST)
DECODER_MERGED_INFO = safe_decoder_info(DECODER_MERGED_PATH.name, DECODER_MERGED)

# Alias cũ để tránh lỗi nếu bạn từng dùng tên *_TOKEN_ID ở các đoạn thử nghiệm.
PAD_TOKEN_ID = PAD_ID
EOS_TOKEN_ID = EOS_ID
BOS_TOKEN_ID = BOS_ID
DECODER_START_TOKEN_ID = DECODER_START_ID

SOURCE_CONTENT_LIMIT = max(1, MAX_SOURCE_LENGTH - 1)
# Giới hạn riêng cho chia chunk. Encoder vẫn nhận tối đa SOURCE_CONTENT_LIMIT,
# nhưng văn bản dài sẽ được chia nhỏ hơn để output tiếng Việt không bị cụt quanh 127 token.
REQUESTED_CHUNK_SOURCE_LIMIT = int(os.environ.get("CHUNK_SOURCE_LIMIT", "40"))
CHUNK_SOURCE_LIMIT = max(8, min(REQUESTED_CHUNK_SOURCE_LIMIT, SOURCE_CONTENT_LIMIT))


def source_token_count(text: str) -> int:
    return len(TOKENIZER.encode(text))



class TinyCNNChunker:
    """ONNX character-level boundary predictor.

    Files expected in CHUNKER_DIR:
      - chunk_boundary_cnn.onnx      input: character ids, output: logits [batch, seq, 2]
      - chunk_char_vocab.json        mapping char -> id
      - chunk_boundary_config.json   contains max_len and best_threshold
    """

    def __init__(self, onnx_path: Path, vocab_path: Path, config_path: Path):
        self.onnx_path = onnx_path
        self.vocab_path = vocab_path
        self.config_path = config_path
        self.config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
        raw_vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
        if isinstance(raw_vocab, dict) and "char_to_id" in raw_vocab:
            raw_vocab = raw_vocab["char_to_id"]
        if not isinstance(raw_vocab, dict):
            raise RuntimeError("chunk_char_vocab.json không phải dict char -> id")
        self.vocab = {str(k): int(v) for k, v in raw_vocab.items()}
        self.pad_id = int(self.config.get("pad_id", self.vocab.get("<pad>", 0)))
        self.unk_id = int(self.config.get("unk_id", self.vocab.get("<unk>", 1)))
        self.max_len = int(self.config.get("max_len", 256))
        env_thr = CHUNKER_THRESHOLD
        self.threshold = float(env_thr) if env_thr else float(self.config.get("best_threshold", 0.8))
        self.session = ort.InferenceSession(str(onnx_path), sess_options=OPTIONS, providers=PROVIDERS)
        self.inputs = list(self.session.get_inputs())
        self.input_names = [x.name for x in self.inputs]
        self.output_name = self.session.get_outputs()[0].name

        # TinyCNNChunker bản train của bạn có thể có 1 input hoặc 2 input:
        #   input_ids
        #   attention_mask
        # Bản cũ chỉ feed input_ids nên ONNX báo thiếu attention_mask.
        self.ids_name = find_name(self.input_names, ["input_ids", "ids"], ["input"])
        if self.ids_name is None:
            self.ids_name = self.input_names[0]
        self.mask_name = find_name(
            self.input_names,
            ["attention_mask", "mask", "input_mask"],
            ["mask"],
        )
        self.input_types = {x.name: x.type for x in self.inputs}

    def _np_dtype_for_input(self, name: str) -> np.dtype:
        typ = self.input_types.get(name, "").lower()
        # ONNX export của TinyCNNChunker có thể khai báo input_ids là tensor(float)
        # dù nội dung vẫn là character ids. Phải feed đúng dtype theo graph,
        # nếu không ORT báo: expected tensor(float), actual tensor(int64).
        if "float16" in typ:
            return np.float16
        if "float" in typ:
            return np.float32
        if "double" in typ:
            return np.float64
        if "int32" in typ:
            return np.int32
        if "int64" in typ:
            return np.int64
        if "bool" in typ:
            return np.bool_
        return np.int64

    def encode_inputs(self, text: str) -> tuple[str, np.ndarray, np.ndarray | None]:
        window = text[:self.max_len]
        ids = [self.vocab.get(ch, self.unk_id) for ch in window]
        if not ids:
            ids = [self.pad_id]
            real_len = 1
        else:
            real_len = len(ids)
        arr = np.asarray([ids], dtype=self._np_dtype_for_input(self.ids_name))
        mask = None
        if self.mask_name is not None:
            if self._np_dtype_for_input(self.mask_name) == np.bool_:
                mask = np.asarray([[True] * real_len], dtype=np.bool_)
            else:
                mask = np.asarray([[1] * real_len], dtype=self._np_dtype_for_input(self.mask_name))
        return window, arr, mask

    def boundary_probs(self, text: str) -> np.ndarray:
        window, arr, mask = self.encode_inputs(text)
        feeds: dict[str, np.ndarray] = {self.ids_name: arr}
        if self.mask_name is not None and mask is not None:
            feeds[self.mask_name] = mask

        # Nếu export có input phụ hiếm gặp, feed zero hợp shape để khỏi chết.
        for meta in self.inputs:
            if meta.name in feeds:
                continue
            shape = []
            for dim in meta.shape:
                if isinstance(dim, int) and dim > 0:
                    shape.append(dim)
                else:
                    shape.append(arr.shape[1] if "seq" in str(dim).lower() else arr.shape[0])
            feeds[meta.name] = np.zeros(shape, dtype=ort_dtype(meta.type))

        logits = self.session.run([self.output_name], feeds)[0]
        logits = np.asarray(logits[0, :len(window), :], dtype=np.float32)
        logits = logits - logits.max(axis=-1, keepdims=True)
        exp = np.exp(logits)
        probs = exp / exp.sum(axis=-1, keepdims=True)
        return probs[:, 1]


CHUNKER: TinyCNNChunker | None = None
if USE_CHUNKER:
    try:
        if CHUNKER_ONNX_PATH.is_file() and CHUNKER_VOCAB_PATH.is_file():
            CHUNKER = TinyCNNChunker(CHUNKER_ONNX_PATH, CHUNKER_VOCAB_PATH, CHUNKER_CONFIG_PATH)
        else:
            print(f"[WARN] Không thấy chunker tại {CHUNKER_DIR}, dùng rule fallback khi cần chia.")
    except Exception as exc:
        print(f"[WARN] Không load được TinyCNNChunker: {type(exc).__name__}: {exc}")
        CHUNKER = None


def _fallback_cut_by_token_budget(text: str, limit: int) -> int:
    """Cắt ký tự cuối cùng sao cho prefix không vượt limit token."""
    last_good = 0
    for i in range(1, len(text) + 1):
        if source_token_count(text[:i]) <= limit:
            last_good = i
        else:
            break
    return max(1, last_good)


def _rule_cut_candidates(text: str, limit: int, min_tokens: int) -> list[tuple[int, int, float, str]]:
    """Fallback rule: trả về candidates (cut_char_index, token_count, score, reason)."""
    hard = set("。！？!?；;\n")
    soft = set("，、：:,")
    close = set("”’」』》）)]}")
    candidates: list[tuple[int, int, float, str]] = []
    last_good = 0
    for i, ch in enumerate(text[:512]):
        n = source_token_count(text[:i + 1])
        if n > limit:
            break
        last_good = i + 1
        # Cắt sau ngoặc đóng nếu ngay trước nó là dấu kết câu.
        prev = text[i - 1] if i > 0 else ""
        if ch in hard or (ch in close and prev in hard):
            if n >= min_tokens:
                candidates.append((i + 1, n, 1.0 + n / limit, "rule_hard"))
        elif ch in soft:
            if n >= min_tokens:
                candidates.append((i + 1, n, 0.55 + n / limit, "rule_soft"))
    if candidates:
        return candidates
    if last_good > 0:
        return [(last_good, source_token_count(text[:last_good]), 0.1, "rule_last_good")]
    return [(1, source_token_count(text[:1]), 0.0, "rule_force_1")]


def choose_model_cut(text: str, limit: int = SOURCE_CONTENT_LIMIT) -> tuple[int, str, float, int]:
    """Chọn vị trí cắt bằng TinyCNNChunker, luôn bảo đảm prefix <= limit token.

    Trả về: (char_cut_index, reason, score_or_prob, prefix_tokens)
    """
    text = text.strip()
    if not text:
        return 0, "empty", 0.0, 0
    full_tokens = source_token_count(text)
    if full_tokens <= limit:
        return len(text), "whole", 1.0, full_tokens

    min_tokens = max(1, int(limit * CHUNKER_MIN_FILL_RATIO))

    if CHUNKER is not None:
        window = text[:CHUNKER.max_len]
        try:
            probs = CHUNKER.boundary_probs(window)
            strong: list[tuple[int, int, float, str]] = []
            weak: list[tuple[int, int, float, str]] = []
            last_good = 0
            last_good_tokens = 0
            for i, prob in enumerate(probs):
                prefix = text[:i + 1]
                n = source_token_count(prefix)
                if n > limit:
                    break
                last_good = i + 1
                last_good_tokens = n
                p = float(prob)
                if n >= min_tokens:
                    # Điểm số ưu tiên vừa gần đầy context vừa có xác suất boundary cao.
                    score = p * 2.0 + (n / limit)
                    if p >= CHUNKER.threshold:
                        strong.append((i + 1, n, score, f"cnn_thr_{p:.2f}"))
                    elif p >= 0.25:
                        weak.append((i + 1, n, score, f"cnn_weak_{p:.2f}"))
            if strong:
                cut, n, score, reason = max(strong, key=lambda x: x[2])
                return cut, reason, score, n
            if weak:
                cut, n, score, reason = max(weak, key=lambda x: x[2])
                return cut, reason, score, n
            if last_good > 0:
                # Nếu model không tự tin, rơi qua rule trong vùng đã biết không overflow.
                rule = _rule_cut_candidates(text[:last_good], limit, min_tokens)
                cut, n, score, reason = max(rule, key=lambda x: x[2])
                return cut, "cnn_no_hit_" + reason, score, n
        except Exception as exc:
            print(f"[WARN] Chunker lỗi, fallback rule: {type(exc).__name__}: {exc}")

    rule = _rule_cut_candidates(text, limit, min_tokens)
    cut, n, score, reason = max(rule, key=lambda x: x[2])
    return cut, reason, score, n


def split_text_by_token_limit(text: str, limit: int = CHUNK_SOURCE_LIMIT) -> list[str]:
    """Chia input bằng model boundary thay vì cắt cứng 128 token.

    Mục tiêu: mỗi chunk <= limit source token, ưu tiên vị trí model dự đoán là boundary.
    """
    text = text.strip()
    if not text:
        return []
    if source_token_count(text) <= limit:
        return [text]

    chunks: list[str] = []
    rest = text
    guard = 0
    while rest and source_token_count(rest) > limit:
        guard += 1
        if guard > 1000:
            raise RuntimeError("split_text_by_token_limit guard overflow")
        cut, reason, score, n = choose_model_cut(rest, limit)
        if cut <= 0:
            cut = _fallback_cut_by_token_budget(rest, limit)
            reason, score, n = "fallback_bad_cut", 0.0, source_token_count(rest[:cut])
        piece = rest[:cut].strip()
        if not piece:
            cut = _fallback_cut_by_token_budget(rest, limit)
            piece = rest[:cut].strip()
            reason, score, n = "fallback_empty_piece", 0.0, source_token_count(piece)
        chunks.append(piece)
        print(f"[CHUNKER] cut={cut} src_tokens={source_token_count(piece)} reason={reason} score={score:.3f} preview={piece[-24:]!r}")
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return chunks

def encode_source(
    text: str,
) -> tuple[np.ndarray, np.ndarray]:
    token_ids = TOKENIZER.encode(text)

    # Chừa một vị trí cuối cho EOS.
    token_ids = token_ids[:MAX_SOURCE_LENGTH - 1]

    if (
        not token_ids
        or token_ids[-1] != EOS_TOKEN_ID
    ):
        token_ids.append(EOS_TOKEN_ID)

    real_length = len(token_ids)

    attention_mask = (
        [1] * real_length
        + [0] * (MAX_SOURCE_LENGTH - real_length)
    )

    token_ids = (
        token_ids
        + [PAD_TOKEN_ID]
        * (MAX_SOURCE_LENGTH - real_length)
    )

    return (
        np.asarray(
            [token_ids],
            dtype=np.int64,
        ),
        np.asarray(
            [attention_mask],
            dtype=np.int64,
        ),
    )


def run_encoder(ids: np.ndarray, mask: np.ndarray) -> np.ndarray:
    feeds = {ENC_INPUT: ids}
    if ENC_MASK:
        feeds[ENC_MASK] = mask
    outputs = ENCODER.run(None, feeds)
    return np.asarray(outputs[0])


def run_decoder(ids: np.ndarray, hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    # Fallback không cache: giữ để máy nào thiếu decoder_with_past/merged vẫn chạy được.
    return run_decoder_full(DECODER_INFO, ids, hidden, mask)


def decode_output_ids(generated: list[int]) -> str:
    output_ids = [i for i in generated[1:] if i not in {PAD_ID, BOS_ID, EOS_ID, DECODER_START_ID}]
    return TOKENIZER.decode(output_ids).strip()


def _banned_ngram_tokens(generated: list[int], ngram_size: int) -> set[int]:
    """Tìm các token sẽ tái tạo một n-gram đã xuất hiện trước đó trong chuỗi đã sinh.

    Đây là kỹ thuật no-repeat-ngram tiêu chuẩn (giống HF generate): nếu (n-1) token
    cuối cùng đã từng đứng trước một token cụ thể, cấm sinh lại đúng token đó ở bước này,
    để tránh mô hình lặp lại nguyên cụm từ/câu (lỗi thường gặp khi decode greedy).
    """
    if ngram_size <= 0 or len(generated) < ngram_size:
        return set()
    prefix = tuple(generated[-(ngram_size - 1):])
    banned: set[int] = set()
    for i in range(len(generated) - ngram_size + 1):
        if tuple(generated[i:i + ngram_size - 1]) == prefix:
            banned.add(generated[i + ngram_size - 1])
    return banned


def _apply_generation_penalties(
    logits_last: np.ndarray,
    generated: list[int],
    penalty: float,
    ngram_size: int,
    min_new_tokens: int,
) -> np.ndarray:
    logits = logits_last.copy()
    # Phạt lũy thừa theo số lần token đã xuất hiện, không phải phạt cố định 1 lần.
    # Bản cũ chỉ trừng phạt mỗi token 1 lần dù nó đã lặp bao nhiêu lần, nên khi model
    # nhỏ rơi vào vòng lặp kiểu "một một X một một Y..." (bigram lặp, khác token đệm ở
    # giữa nên no-repeat-ngram=3 không chặn được), token bị kẹt vẫn thắng argmax vì chỉ
    # bị chia 1 lần cho REPETITION_PENALTY. Phạt lũy thừa theo count khiến token càng lặp
    # càng bị đè mạnh, thoát vòng lặp mà không cần đổi sang beam search.
    for token_id, count in Counter(generated).items():
        if token_id in {PAD_ID, BOS_ID, EOS_ID, DECODER_START_ID}:
            continue
        scaled = penalty ** count
        if logits[token_id] > 0:
            logits[token_id] /= scaled
        else:
            logits[token_id] *= scaled

    for token_id in _banned_ngram_tokens(generated, ngram_size):
        if token_id not in {PAD_ID, BOS_ID, EOS_ID, DECODER_START_ID}:
            logits[token_id] = -1e9

    # generated[0] luôn là DECODER_START_ID nên số token thực sự đã sinh là len(generated) - 1.
    if min_new_tokens > 0 and (len(generated) - 1) < min_new_tokens:
        logits[EOS_ID] = -1e9

    return logits


def get_next_token_id(
    logits_last: np.ndarray,
    generated: list[int],
    penalty: float = REPETITION_PENALTY,
    ngram_size: int = NO_REPEAT_NGRAM_SIZE,
    min_new_tokens: int = MIN_NEW_TOKENS,
) -> int:
    logits = _apply_generation_penalties(logits_last, generated, penalty, ngram_size, min_new_tokens)
    return int(np.argmax(logits))


def translate_no_cache(hidden: np.ndarray, mask: np.ndarray, max_new_tokens: int) -> tuple[list[int], str]:
    generated = [DECODER_START_ID]
    for _ in range(max_new_tokens):
        decoder_ids = np.asarray([generated], dtype=np.int64)
        logits = run_decoder(decoder_ids, hidden, mask)
        next_id = get_next_token_id(logits[0, -1, :], generated)
        if next_id == EOS_ID:
            break
        generated.append(next_id)
    return generated, "no_cache"


def translate_with_merged_cache(hidden: np.ndarray, mask: np.ndarray, max_new_tokens: int) -> tuple[list[int], str]:
    if DECODER_MERGED_INFO is None or not DECODER_MERGED_INFO.can_cache:
        raise RuntimeError("decoder_model_merged.onnx không hỗ trợ cache")
    info = DECODER_MERGED_INFO
    generated = [DECODER_START_ID]
    past: dict[str, np.ndarray] | None = None
    for step in range(max_new_tokens):
        token = generated[-1]
        decoder_ids = np.asarray([[token]], dtype=np.int64)
        logits, past = run_decoder_cached(
            info,
            decoder_ids,
            hidden,
            mask,
            use_cache=step > 0,
            past=past,
            position=step,
        )
        next_id = get_next_token_id(logits[0, -1, :], generated)
        if next_id == EOS_ID:
            break
        generated.append(next_id)
    return generated, "merged_cache"


def translate_with_two_decoder_cache(hidden: np.ndarray, mask: np.ndarray, max_new_tokens: int) -> tuple[list[int], str]:
    if DECODER_WITH_PAST_INFO is None:
        raise RuntimeError("Thiếu decoder_with_past_model.onnx")
    if not DECODER_INFO.has_present:
        raise RuntimeError("decoder_model.onnx không xuất present.* cache")
    if not DECODER_WITH_PAST_INFO.can_cache:
        raise RuntimeError("decoder_with_past_model.onnx không nhận/xuất decoder past cache")

    generated = [DECODER_START_ID]

    # Bước 1: chạy decoder_model.onnx với decoder_start để lấy token đầu tiên
    # và toàn bộ present.* cache, gồm cả self-attention decoder cache lẫn cross-attention encoder cache.
    first_ids = np.asarray([[DECODER_START_ID]], dtype=np.int64)
    logits, first_present = run_decoder_first_present(DECODER_INFO, first_ids, hidden, mask)

    # Map present.N.xxx từ decoder_model.onnx sang past_key_values.N.xxx của decoder_with_past_model.onnx.
    past: dict[str, np.ndarray] = {}
    missing: list[str] = []
    for past_meta in DECODER_WITH_PAST_INFO.past_inputs:
        past_name = past_meta.name
        present_name = past_name.replace("past_key_values", "present")
        value = first_present.get(present_name)
        if value is None:
            # Fallback mềm cho vài export đặt tên hơi khác.
            wanted = DecoderInfo.norm_cache_name(past_name)
            for out_name, arr in first_present.items():
                if DecoderInfo.norm_cache_name(out_name) == wanted:
                    value = arr
                    break
        if value is None:
            missing.append(past_name)
        else:
            past[past_name] = value

    if missing:
        raise RuntimeError(
            "Không map đủ present cache từ decoder_model.onnx sang decoder_with_past_model.onnx; "
            f"thiếu {len(missing)} input, ví dụ: {missing[:4]}"
        )

    next_id = get_next_token_id(logits[0, -1, :], generated)
    if next_id == EOS_ID:
        return generated, "two_decoder_cache"
    generated.append(next_id)

    # Bước 2 trở đi: chỉ đưa token mới nhất + past cache.
    # decoder_with_past_model.onnx chỉ xuất present.*.decoder.*, nên phải giữ nguyên encoder cache cũ.
    for step in range(1, max_new_tokens):
        decoder_ids = np.asarray([[generated[-1]]], dtype=np.int64)
        logits, updated_decoder_past = run_decoder_cached(
            DECODER_WITH_PAST_INFO,
            decoder_ids,
            hidden,
            mask,
            use_cache=True,
            past=past,
            position=step,
        )
        past.update(updated_decoder_past)
        next_id = get_next_token_id(logits[0, -1, :], generated)
        if next_id == EOS_ID:
            break
        generated.append(next_id)
    return generated, "two_decoder_cache"


CACHE_FAILED_REASON: str | None = None

def translate_one(text: str, max_new_tokens: int = MAX_NEW_TOKENS) -> tuple[str, float, int]:
    text = text.strip()
    if not text:
        return "", 0.0, 0
    started = time.perf_counter()
    source_ids, mask = encode_source(text)
    hidden = run_encoder(source_ids, mask)

    mode = "no_cache"
    global CACHE_FAILED_REASON
    try:
        if CACHE_MODE in {"0", "false", "off", "none", "no_cache"}:
            generated, mode = translate_no_cache(hidden, mask, max_new_tokens)
        elif CACHE_FAILED_REASON:
            generated, mode = translate_no_cache(hidden, mask, max_new_tokens)
        elif CACHE_MODE == "merged":
            generated, mode = translate_with_merged_cache(hidden, mask, max_new_tokens)
        elif DECODER_WITH_PAST_INFO is not None and DECODER_INFO.has_present and DECODER_WITH_PAST_INFO.can_cache:
            generated, mode = translate_with_two_decoder_cache(hidden, mask, max_new_tokens)
        else:
            # Mặc định KHÔNG dùng merged trên Android vì vài file Optimum merged bị lỗi MatMul broadcast.
            # Muốn ép thử: ORT_CACHE=merged python app.py
            generated, mode = translate_no_cache(hidden, mask, max_new_tokens)
    except Exception as exc:
        # Cache lệch input/output thì tự rơi về bản cũ, chỉ báo 1 dòng, không phun traceback dài.
        CACHE_FAILED_REASON = f"{type(exc).__name__}: {exc}"
        print(f"[WARN] Cache lỗi, fallback no_cache: {CACHE_FAILED_REASON}")
        generated, mode = translate_no_cache(hidden, mask, max_new_tokens)

    output_ids = [i for i in generated[1:] if i not in {PAD_ID, BOS_ID, EOS_ID, DECODER_START_ID}]
    result = TOKENIZER.decode(output_ids).strip()
    elapsed = time.perf_counter() - started
    print(f"[GEN] mode={mode} tokens={len(output_ids)} time={elapsed:.2f}s")
    return result, elapsed, len(output_ids)


def translate(text: str, max_new_tokens: int = MAX_NEW_TOKENS) -> tuple[str, float, int]:
    text = text.strip()
    if not text:
        return "", 0.0, 0

    token_count = source_token_count(text)

    if token_count <= CHUNK_SOURCE_LIMIT:
        return translate_one(text, max_new_tokens)

    if not CHUNK_LONG_INPUT:
        msg = (
            f"Input quá dài: {token_count} token, trong khi ONNX encoder hiện tại chỉ nhận tối đa "
            f"{SOURCE_CONTENT_LIMIT} token nội dung + EOS = {MAX_SOURCE_LENGTH}. "
            "Không thể tăng MAX_SOURCE_LENGTH lên 256/512 với file ONNX này vì sẽ lỗi broadcast 128 by 512. "
            "MAX_NEW_TOKENS chỉ tăng độ dài đầu ra, không tăng giới hạn đầu vào. "
            "Muốn dịch nguyên đoạn dài không chia chunk thì cần export/train lại model với max_source_positions lớn hơn. "
            "Muốn dùng tạm đoạn đầu, chạy STRICT_SOURCE_LIMIT=0; muốn chia tự động, chạy CHUNK_LONG_INPUT=1."
        )
        if STRICT_SOURCE_LIMIT:
            raise ValueError(msg)
        print(f"[WARN] {msg}")
        return translate_one(text, max_new_tokens)

    started = time.perf_counter()
    chunks = split_text_by_token_limit(text, CHUNK_SOURCE_LIMIT)
    print(f"[SMART_SPLIT] input_tokens={token_count} chunks={len(chunks)} chunk_limit={CHUNK_SOURCE_LIMIT} model_limit={SOURCE_CONTENT_LIMIT} chunker={CHUNKER is not None}")

    outputs: list[str] = []
    total_tokens = 0
    for idx, chunk in enumerate(chunks, 1):
        print(f"[SMART_SPLIT] chunk {idx}/{len(chunks)} src_tokens={source_token_count(chunk)}")
        translated, _elapsed, out_tokens = translate_one(chunk, max_new_tokens)
        if translated:
            outputs.append(translated)
        total_tokens += out_tokens

    elapsed = time.perf_counter() - started
    # Xuống dòng giữa các khúc để tránh dính câu. Bạn có thể đổi thành " " nếu thích một đoạn liền.
    result = "\n".join(outputs).strip()
    print(f"[GEN] mode=chunker_chunks chunks={len(chunks)} total_tokens={total_tokens} time={elapsed:.2f}s")
    return result, elapsed, total_tokens


PAGE = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dịch Trung → Việt</title>
<style>
:root{color-scheme:dark;--bg:#0e1217;--card:#171d24;--line:#2d3944;--text:#f3f6f8;--muted:#9ba9b5;--accent:#62ded5;--danger:#ff9292}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at top right,#183139 0,transparent 34%),var(--bg);color:var(--text);font-family:system-ui,sans-serif}main{width:min(900px,100%);margin:auto;padding:22px 14px 40px}h1{margin:0 0 4px}.sub{margin:0 0 20px;color:var(--muted)}.grid{display:grid;gap:14px}.card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:16px}label{display:block;margin-bottom:9px;font-weight:750}textarea{width:100%;min-height:170px;resize:vertical;border:1px solid #34434f;border-radius:15px;padding:14px;background:#0c1116;color:var(--text);font:inherit;font-size:17px;line-height:1.55;outline:none}textarea:focus{border-color:var(--accent)}.actions{display:flex;gap:10px;margin-top:12px}button{min-height:50px;border:0;border-radius:14px;padding:0 18px;font:inherit;font-weight:800}#go{flex:1;background:var(--accent);color:#071413}#clear{background:#2b3640;color:var(--text)}button:disabled{opacity:.55}#status{min-height:22px;margin-top:10px;color:var(--muted)}.error{color:var(--danger)!important}.meta{margin-top:10px;color:var(--muted);font-size:13px}@media(min-width:760px){.grid{grid-template-columns:1fr 1fr}}
</style></head><body><main><h1>Dịch Trung → Việt</h1><p class="sub">ONNX Runtime chạy trực tiếp trên Android</p><div class="grid"><section class="card"><label for="src">Tiếng Trung</label><textarea id="src" placeholder="Nhập câu tiếng Trung..."></textarea><div class="actions"><button id="go">Dịch</button><button id="clear">Xóa</button></div><div id="status"></div></section><section class="card"><label for="dst">Tiếng Việt</label><textarea id="dst" readonly placeholder="Bản dịch sẽ xuất hiện ở đây..."></textarea><div class="meta" id="meta"></div></section></div></main>
<script>
const src=document.getElementById('src'),dst=document.getElementById('dst'),go=document.getElementById('go'),clear=document.getElementById('clear'),statusBox=document.getElementById('status'),meta=document.getElementById('meta');
async function run(){const text=src.value.trim();if(!text){statusBox.textContent='Chưa nhập câu tiếng Trung.';statusBox.className='error';return}go.disabled=true;clear.disabled=true;dst.value='';meta.textContent='';statusBox.textContent='Đang dịch...';statusBox.className='';try{const r=await fetch('/translate',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({text})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Dịch thất bại');dst.value=d.translation;statusBox.textContent='Hoàn thành.';meta.textContent=`${d.time.toFixed(2)} giây · ${d.tokens} token`}catch(e){statusBox.textContent='Lỗi: '+e.message;statusBox.className='error'}finally{go.disabled=false;clear.disabled=false}}
go.onclick=run;clear.onclick=()=>{src.value='';dst.value='';statusBox.textContent='';statusBox.className='';meta.textContent='';src.focus()};src.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='Enter')run()});
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print("[HTTP] " + fmt % args)

    def send_bytes(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status: int, data: dict[str, Any]) -> None:
        self.send_bytes(status, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_bytes(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif self.path == "/health":
            self.send_json(200, {"ok": True, "providers": PROVIDERS, "model_dir": str(MODEL_DIR)})
        else:
            self.send_json(404, {"error": "Không tìm thấy đường dẫn"})

    def do_POST(self) -> None:
        if self.path != "/translate":
            self.send_json(404, {"error": "Không tìm thấy đường dẫn"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            text = parse_qs(body, keep_blank_values=True).get("text", [""])[0].strip()
            if not text:
                self.send_json(400, {"error": "Chưa nhập câu tiếng Trung"})
                return
            translation, elapsed, token_count = translate(text)
            self.send_json(200, {"translation": translation, "time": elapsed, "tokens": token_count})
        except Exception as exc:
            traceback.print_exc()
            self.send_json(500, {"error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    probe = "服务器的响应时间降低了百分之十五。"
    probe_ids = TOKENIZER.encode(probe)
    probe_back = TOKENIZER.decode(probe_ids)
    print("=" * 72)
    print("TOKENIZER PROBE")
    print("Text   :", probe)
    print("IDs    :", probe_ids)
    print("Decode :", probe_back)
    print("=" * 72)
    print("ORT version:", ort.__version__)
    print("Providers  :", PROVIDERS)
    print("Model dir  :", MODEL_DIR)
    print("Encoder   :", ENCODER_PATH)
    print("Decoder   :", DECODER_PATH)
    if DECODER_WITH_PAST_PATH.is_file():
        print("Past file :", DECODER_WITH_PAST_PATH)
    if DECODER_MERGED_PATH.is_file():
        print("Merged file:", DECODER_MERGED_PATH)
    print("Tokenizer :", TOKENIZER_PATH)
    print("Config    :", CONFIG_PATH)
    print("Encoder EP :", ENCODER.get_providers())
    print("Decoder EP :", DECODER.get_providers())
    if DECODER_WITH_PAST is not None:
        print("Past EP    :", DECODER_WITH_PAST.get_providers())
    if DECODER_MERGED is not None:
        print("Merged EP  :", DECODER_MERGED.get_providers())
    if CACHE_MODE in {"0", "false", "off", "none", "no_cache"}:
        cache_mode = "off"
    elif CACHE_MODE == "merged" and DECODER_MERGED_INFO is not None and DECODER_MERGED_INFO.can_cache:
        cache_mode = "merged_forced"
    elif DECODER_WITH_PAST_INFO is not None and DECODER_INFO.has_present and DECODER_WITH_PAST_INFO.can_cache:
        cache_mode = "two_decoder"
    else:
        cache_mode = "off"
    print("Cache mode :", cache_mode)
    print("Cache env  :", CACHE_MODE)
    print("Max source :", MAX_SOURCE_LENGTH)
    print("Requested  :", REQUESTED_MAX_SOURCE_LENGTH)
    print("Model max  :", MODEL_MAX_SOURCE_LENGTH)
    print("Chunk limit:", CHUNK_SOURCE_LIMIT, "(requested", REQUESTED_CHUNK_SOURCE_LIMIT, ")")
    print("Chunk input:", CHUNK_LONG_INPUT)
    print("Chunker   :", "on" if CHUNKER is not None else "off")
    if CHUNKER is not None:
        print("Chunker dir:", CHUNKER_DIR)
        print("Chunker onnx:", CHUNKER_ONNX_PATH)
        print("Chunker vocab:", CHUNKER_VOCAB_PATH)
        print("Chunker cfg:", CHUNKER_CONFIG_PATH)
        print("Chunker thr:", CHUNKER.threshold)
        print("Chunker max:", CHUNKER.max_len)
        print("Chunker inputs:", CHUNKER.input_names)
    print("Strict src :", STRICT_SOURCE_LIMIT)
    print("Max new    :", MAX_NEW_TOKENS)
    print("Threads    :", THREADS)
    print(f"Mở tại     : http://{HOST}:{PORT}")
    print("Dừng       : Ctrl+C")
    print("=" * 72)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang dừng...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
