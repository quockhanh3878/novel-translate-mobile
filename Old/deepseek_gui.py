"""
deepseek_gui.py - GUI cho quy trinh Cao -> Dich (DeepSeek API) -> Dong goi EPUB,
chay tung buoc co the theo doi, RESUME duoc (dua thang vao crawl_novel()/
translate_novel() - tu dong dem so chuong da co san tren dia va tiep tuc tu do,
khong dich/cao lai tu dau).

Khac novel_gui.py (dich bang MarianMT cuc bo, khong resume that su - moi lan chay
dich lai toan bo trong RAM): file nay khong import app.py, dung DeepSeek API va
glossary.json + style-guide prompt de dam bao chat luong dong nhat, va moi buoc deu
ghi thang xuong file nen bam "Dung" giua chung roi chay lai se tiep tuc dung cho.

Su dung:
    .venv\\Scripts\\python deepseek_gui.py
"""

import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from crawler import DEFAULT_START_URL, DEFAULT_OUTPUT, count_chapters, crawl_novel
from deepseek_translate import load_dotenv, load_glossary, save_glossary, translate_novel
from build_epub import build_epub

BG_COLOR = "#1e1e1e"
CARD_COLOR = "#2d2d2d"
TEXT_COLOR = "#e0e0e0"
ACCENT_COLOR = "#007acc"
TEXT_MUTED = "#888888"

DEFAULT_GLOSSARY_TEXT = (
    "王八喜: Vương Bát Hỉ\n"
    "任九贵: Nhậm Cửu Quý\n"
    "尹白鸽: Doãn Bạch Cát\n"
    "纪震: Kỷ Chấn\n"
    "谢远航: Tạ Viễn Hàng\n"
    "华登峰: Hoa Đăng Phong\n"
    "牛再山: Ngưu Tái Sơn\n"
    "牛松: Ngưu Tùng\n"
    "上官: Thượng Quan\n"
    "上官顺敏: Thượng Quan Thuận Mẫn\n"
    "常书欣: Thường Thư Hân\n"
)


def glossary_to_text(glossary: dict) -> str:
    return "\n".join(f"{zh}: {vi}" for zh, vi in glossary.items()) + ("\n" if glossary else "")


def text_to_glossary(text: str) -> dict:
    glossary = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        zh, _, vi = line.partition(":")
        zh, vi = zh.strip(), vi.strip()
        if zh and vi:
            glossary[zh] = vi
    return glossary


class AppGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DeepSeek Novel Translator & EPUB Packager")
        self.geometry("980x680")
        self.configure(bg=BG_COLOR)

        self.log_queue = queue.Queue()
        self.is_running = False
        self.abort_requested = False

        load_dotenv()

        self.setup_styles()
        self.create_widgets()
        self.after(100, self.process_logs)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(".", background=BG_COLOR, foreground=TEXT_COLOR, fieldbackground=CARD_COLOR)
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=TEXT_COLOR, font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("TEntry", fieldbackground=CARD_COLOR, foreground=TEXT_COLOR, font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=BG_COLOR, foreground=TEXT_COLOR)
        style.configure("TProgressbar", thickness=15)
        style.configure("Primary.TButton", background=ACCENT_COLOR, foreground="#ffffff",
                         font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#005999")])
        style.configure("Stop.TButton", background="#c62828", foreground="#ffffff",
                         font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Stop.TButton", background=[("active", "#b71c1c")])

    def create_widgets(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_config = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_config, text="Cấu hình")
        self.tab_logs = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_logs, text="Tiến trình")

        self.setup_tab_config()
        self.setup_tab_logs()

    def setup_tab_config(self):
        self.tab_config.columnconfigure(0, weight=1)
        self.tab_config.columnconfigure(1, weight=1)
        self.tab_config.rowconfigure(0, weight=1)

        left = ttk.Frame(self.tab_config, padding=20)
        left.grid(row=0, column=0, sticky="nsew")

        ttk.Label(left, text="Quy trình: Cào → Dịch (DeepSeek) → EPUB", style="Header.TLabel").pack(
            anchor="w", pady=(0, 15))

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        api_status = "✓ Đã nạp DEEPSEEK_API_KEY từ .env" if api_key else "✗ Thiếu DEEPSEEK_API_KEY (tạo file .env)"
        api_color = "#2ea44f" if api_key else "#c62828"
        self.lbl_api_status = tk.Label(left, text=api_status, bg=BG_COLOR, fg=api_color, font=("Segoe UI", 9, "bold"))
        self.lbl_api_status.pack(anchor="w", pady=(0, 15))

        ttk.Label(left, text="URL chương 1 (bỏ trống nếu đã có sẵn file thô):").pack(anchor="w", pady=2)
        self.ent_url = ttk.Entry(left, width=70)
        self.ent_url.pack(fill="x", pady=(0, 10))
        self.ent_url.insert(0, DEFAULT_START_URL)

        ttk.Label(left, text="File truyện thô (đã cào):").pack(anchor="w", pady=2)
        self.ent_raw = ttk.Entry(left, width=70)
        self.ent_raw.pack(fill="x", pady=(0, 10))
        self.ent_raw.insert(0, DEFAULT_OUTPUT)

        ttk.Label(left, text="File bản dịch tiếng Việt:").pack(anchor="w", pady=2)
        self.ent_translated = ttk.Entry(left, width=70)
        self.ent_translated.pack(fill="x", pady=(0, 10))
        self.ent_translated.insert(0, DEFAULT_OUTPUT + ".viet.txt")

        ttk.Label(left, text="Tên Truyện (EPUB Metadata):").pack(anchor="w", pady=2)
        self.ent_title = ttk.Entry(left, width=70)
        self.ent_title.pack(fill="x", pady=(0, 10))
        self.ent_title.insert(0, "Đệ Tam Trùng Nhân Cách")

        ttk.Label(left, text="Tác giả:").pack(anchor="w", pady=2)
        self.ent_author = ttk.Entry(left, width=70)
        self.ent_author.pack(fill="x", pady=(0, 10))
        self.ent_author.insert(0, "Thường Thư Hân")

        ttk.Label(left, text="Thư mục lưu file EPUB:").pack(anchor="w", pady=2)
        dir_frame = ttk.Frame(left)
        dir_frame.pack(fill="x", pady=(0, 15))
        self.ent_dir = ttk.Entry(dir_frame)
        self.ent_dir.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.ent_dir.insert(0, os.path.abspath("."))
        ttk.Button(dir_frame, text="Chọn thư mục...", command=self.browse_dir).pack(side="right")

        opts_frame = ttk.Frame(left)
        opts_frame.pack(fill="x", pady=(0, 15))
        opts_frame.columnconfigure((0, 1, 2), weight=1)

        ttk.Label(opts_frame, text="Model:").grid(row=0, column=0, sticky="w")
        self.cbo_model = ttk.Combobox(opts_frame, values=["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"],
                                       state="readonly", width=18)
        self.cbo_model.set("deepseek-v4-flash")
        self.cbo_model.grid(row=1, column=0, sticky="w", pady=(0, 10))

        ttk.Label(opts_frame, text="Số chương dịch song song:").grid(row=0, column=1, sticky="w")
        self.spn_workers = ttk.Spinbox(opts_frame, from_=1, to=8, width=6)
        self.spn_workers.set(1)
        self.spn_workers.grid(row=1, column=1, sticky="w", pady=(0, 10))

        ttk.Label(opts_frame, text="Temperature:").grid(row=0, column=2, sticky="w")
        self.ent_temp = ttk.Entry(opts_frame, width=8)
        self.ent_temp.insert(0, "1.3")
        self.ent_temp.grid(row=1, column=2, sticky="w", pady=(0, 10))

        self.var_thinking = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_frame, text="Bật thinking mode (bắt buộc để dịch đúng - tắt sẽ chỉ echo nguyên văn)",
                         variable=self.var_thinking).grid(row=2, column=0, columnspan=2, sticky="w")
        self.var_style_detect = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_frame, text="Tự phát hiện văn phong từ chương đầu",
                         variable=self.var_style_detect).grid(row=3, column=0, columnspan=2, sticky="w")
        self.var_avoid_peak = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_frame, text="Tránh giờ cao điểm DeepSeek (9-12h, 14-18h giờ Bắc Kinh, giá gấp đôi)",
                         variable=self.var_avoid_peak).grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Label(opts_frame, text="Số chương dịch song song >1 đánh đổi tính nhất quán tên riêng lấy tốc độ.",
                  font=("Segoe UI", 8, "italic"), foreground=TEXT_MUTED).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(5, 0))

        self.btn_start = ttk.Button(left, text="Bắt đầu / Tiếp tục Quy trình", style="Primary.TButton",
                                     command=self.start_process)
        self.btn_start.pack(pady=10, ipadx=20, ipady=5)

        right = ttk.Frame(self.tab_config, padding=20)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="Từ điển nhân vật & Thuật ngữ (Glossary):", style="Header.TLabel").pack(
            anchor="w", pady=(0, 10))
        ttk.Label(right, text="Định dạng: Tên_Trung: Tên_Việt (mỗi dòng 1 từ). Lưu vào glossary.json khi bắt đầu\n"
                               "chạy; tên nhân vật MỚI mà DeepSeek gặp trong lúc dịch sẽ được tự thêm vào đây.",
                  font=("Segoe UI", 9, "italic"), foreground=TEXT_MUTED).pack(anchor="w", pady=(0, 5))
        self.txt_glossary = tk.Text(right, bg="#252526", fg=TEXT_COLOR, font=("Consolas", 10), wrap="none")
        self.txt_glossary.pack(fill="both", expand=True)
        self.reload_glossary_text()

    def reload_glossary_text(self):
        glossary = load_glossary("glossary.json")
        self.txt_glossary.delete(1.0, tk.END)
        self.txt_glossary.insert(tk.END, glossary_to_text(glossary) or DEFAULT_GLOSSARY_TEXT)

    def setup_tab_logs(self):
        frame = ttk.Frame(self.tab_logs, padding=10)
        frame.pack(fill="both", expand=True)

        self.lbl_status = ttk.Label(frame, text="Trạng thái: Đang chờ...", font=("Segoe UI", 10, "italic"))
        self.lbl_status.pack(anchor="w", pady=2)

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 10))

        self.txt_log = tk.Text(frame, bg="#121212", fg="#00ff00", font=("Consolas", 9), wrap="word")
        self.txt_log.pack(fill="both", expand=True, pady=(0, 10))

        ctrl_frame = ttk.Frame(frame)
        ctrl_frame.pack(fill="x")
        self.btn_stop = ttk.Button(ctrl_frame, text="Dừng tiến trình", style="Stop.TButton",
                                    command=self.stop_process, state="disabled")
        self.btn_stop.pack(side="left", padx=5)

    def browse_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.ent_dir.delete(0, tk.END)
            self.ent_dir.insert(0, os.path.abspath(directory))

    def log(self, message):
        self.log_queue.put(message)

    def process_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.txt_log.insert(tk.END, msg + "\n")
            self.txt_log.see(tk.END)
        self.after(100, self.process_logs)

    def start_process(self):
        if self.is_running:
            return

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            messagebox.showerror("Lỗi", "Thiếu DEEPSEEK_API_KEY. Tạo file .env (xem .env.example) rồi khởi động lại.")
            return

        raw_file = self.ent_raw.get().strip()
        start_url = self.ent_url.get().strip()
        if not start_url and not os.path.exists(raw_file):
            messagebox.showerror("Lỗi", f"Không có URL chương 1 và cũng không tìm thấy file thô {raw_file}.")
            return

        try:
            temperature = float(self.ent_temp.get().strip())
            workers = int(self.spn_workers.get())
        except ValueError:
            messagebox.showerror("Lỗi", "Temperature/số worker không hợp lệ.")
            return

        save_glossary("glossary.json", text_to_glossary(self.txt_glossary.get(1.0, tk.END)))

        self.is_running = True
        self.abort_requested = False
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.txt_log.delete(1.0, tk.END)
        self.progress["value"] = 0
        self.notebook.select(1)

        params = dict(
            api_key=api_key,
            start_url=start_url,
            raw_file=raw_file,
            translated_file=self.ent_translated.get().strip(),
            title=self.ent_title.get().strip(),
            author=self.ent_author.get().strip(),
            save_dir=self.ent_dir.get().strip(),
            model=self.cbo_model.get(),
            temperature=temperature,
            workers=workers,
            thinking=self.var_thinking.get(),
            style_detect=self.var_style_detect.get(),
            avoid_peak=self.var_avoid_peak.get(),
        )
        threading.Thread(target=self.run_pipeline, kwargs=params, daemon=True).start()

    def stop_process(self):
        if not self.is_running:
            return
        self.abort_requested = True
        self.log("\n[DỪNG] Đang yêu cầu dừng... sẽ dừng sau chương đang xử lý. Chạy lại để tiếp tục.")
        self.btn_stop.config(state="disabled")

    def on_chapter_progress(self, idx, total, translated):
        self.progress["maximum"] = total
        self.progress["value"] = idx
        self.lbl_status.config(text=f"Bước 2/3: Đang dịch chương {idx}/{total}...")

    def run_pipeline(self, api_key, start_url, raw_file, translated_file, title, author, save_dir,
                      model, temperature, workers, thinking, style_detect, avoid_peak):
        try:
            self.lbl_status.config(text="Bước 1/3: Đang cào truyện...")
            already_raw = count_chapters(raw_file)
            self.log(f"=== Bước 1/3: Cào truyện (đã có {already_raw} chương trong file thô) ===")
            if start_url:
                crawl_novel(start_url, raw_file, log=self.log, should_stop=lambda: self.abort_requested)
            else:
                self.log(f"Bỏ qua cào - dùng file thô có sẵn {raw_file}.")

            if self.abort_requested:
                self.log("[Đã dừng] Chạy lại để tiếp tục từ đây.")
                return

            already_vi = count_chapters(translated_file)
            self.log(f"\n=== Bước 2/3: Dịch bằng DeepSeek API (đã dịch {already_vi} chương) ===")
            self.lbl_status.config(text="Bước 2/3: Đang dịch...")
            translate_novel(
                raw_file, translated_file, "glossary.json", api_key,
                model=model, temperature=temperature, workers=workers, thinking=thinking,
                style_detect=style_detect, log=self.log, on_chapter=self.on_chapter_progress,
                should_stop=lambda: self.abort_requested, avoid_peak=avoid_peak,
            )

            if self.abort_requested:
                self.log("[Đã dừng] Chạy lại để tiếp tục từ đây.")
                return

            self.log("\n=== Bước 3/3: Đóng gói EPUB ===")
            self.lbl_status.config(text="Bước 3/3: Đang đóng gói EPUB...")
            epub_path = os.path.join(save_dir, f"{title}.epub")
            build_epub(translated_file, epub_path, title, author)

            self.log(f"\n[THÀNH CÔNG] Đã lưu EPUB tại: {epub_path}")
            self.lbl_status.config(text="Đã hoàn thành!")
            messagebox.showinfo("Thành công", f"Đã dịch và đóng gói xong EPUB tại:\n{epub_path}")

        except Exception as ex:
            self.log(f"\n[LỖI] {ex}")
            messagebox.showerror("Lỗi", f"Có lỗi xảy ra: {ex}")

        finally:
            self.reload_glossary_text()
            self.finish_ui()

    def finish_ui(self):
        self.is_running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        if not self.abort_requested:
            self.lbl_status.config(text="Trạng thái: Hoàn thành.")


if __name__ == "__main__":
    app = AppGUI()
    app.mainloop()
