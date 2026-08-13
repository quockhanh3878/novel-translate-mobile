import os
import sys
import re
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

# Add current folder to sys.path to import app.py correctly
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

try:
    from app import translate
    from opencc import OpenCC
    from PIL import Image, ImageDraw, ImageFont
    import ebooklib
    from ebooklib import epub
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    sys.exit(1)

# Initialize OpenCC Traditional to Simplified Chinese converter
cc = OpenCC('t2s')

# Dark theme colors
BG_COLOR = "#1e1e1e"
CARD_COLOR = "#2d2d2d"
TEXT_COLOR = "#e0e0e0"
ACCENT_COLOR = "#007acc"
ACCENT_GREEN = "#2ea44f"
TEXT_MUTED = "#888888"

# Placeholder-based translation variables
ZH_PLACEHOLDERS = ['张三', '李四', '王五', '赵六', '钱七', '孙八']
VI_PLACEHOLDERS = ['Trương Tam', 'Lý Tứ', 'Vương Ngũ', 'Triệu Lục', 'Tiền Thất', 'Tôn Bát']


def postprocess(text: str) -> str:
    """
    Cleans up Vietnamese punctuation and spacing issues after translation.
    """
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'^[\s,;.\-!?\u201c\u201d"\']+', '', text)
    text = re.sub(r'\s+([,;.!?])', r'\1', text)
    text = re.sub(r',{2,}', ',', text)
    text = re.sub(r'\.{2,}(?!\.)', '.', text)
    text = re.sub(r'!{2,}', '!', text)
    text = re.sub(r'\?{2,}', '?', text)
    text = re.sub(r'\.,', '.', text)
    text = re.sub(r',\.', '.', text)
    text = re.sub(r'\.\?', '?', text)
    text = re.sub(r'\.\!', '!', text)
    text = re.sub(r',!', '!', text)
    text = re.sub(r',\?', '?', text)
    text = re.sub(r';,', ';', text)
    text = re.sub(r'"\s+', '"', text)
    text = re.sub(r'\s+"', '"', text)
    text = re.sub(r'([.!?])([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÙÚĂĐĨŨƠÀÁÂÃÈÉÊÌÍÒÓÔÙÚĂĐĨŨƠƯỪỨỰỮỬÀÁÂÃÈÉÊÌÍÒÓÔÙÚĂĐĨŨƠ])', r'\1 \2', text)
    text = re.sub(r',([^\s"\')\]0-9])', r', \1', text)
    if text:
        text = text[0].upper() + text[1:]
    def cap_after_punct(m):
        return m.group(1) + m.group(2).upper()
    text = re.sub(r'([.!?]\s+)([a-zàáâãèéêìíòóôùúăđĩũơ])', cap_after_punct, text)
    def cap_after_quote(m):
        return m.group(1) + m.group(2).upper()
    text = re.sub(r'([""])\s*([a-zàáâãèéêìíòóôùúăđĩũơ])', cap_after_quote, text)
    text = re.sub(r'\.\.\.\.+', '...', text)
    text = re.sub(r'[,;]\s*$', '.', text)
    text = re.sub(r':\s*$', '.', text)
    return text.strip()


def translate_clause(clause, glossary=None):
    clause_stripped = clause.strip()
    if not clause_stripped or re.fullmatch(r'[\s\W]+', clause_stripped):
        return ''
        
    active_replacements = []
    temp_clause = clause_stripped
    
    if glossary:
        # Sort names by length descending to prevent substring overlap matching
        sorted_keys = sorted(glossary.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in temp_clause:
                idx = len(active_replacements)
                if idx < len(ZH_PLACEHOLDERS):
                    placeholder = ZH_PLACEHOLDERS[idx]
                    target_name = glossary[key]
                    temp_clause = temp_clause.replace(key, placeholder)
                    active_replacements.append((VI_PLACEHOLDERS[idx], target_name))
                    
    # Convert to Simplified Chinese
    simplified = cc.convert(temp_clause)
    
    # Translate
    translated_text, _, _ = translate(simplified)
    
    # Restore correct Vietnamese names in translated output
    for placeholder_vi, real_name in active_replacements:
        translated_text = re.sub(re.escape(placeholder_vi), real_name, translated_text, flags=re.IGNORECASE)
        
    return translated_text


def translate_paragraph(para, glossary=None):
    if not para.strip():
        return ''
    if re.fullmatch(r'[…\.\!\?\,\;\:\s，。！？；：、「」""''《》〈〉\u2026]+', para):
        return para
    if len(para) <= 40:
        raw = translate_clause(para, glossary)
        return postprocess(raw) if raw else ''

    parts = re.split(r'([，,。．！!？?；;、])', para)
    translated_parts = []
    pending_punct = ''

    punctuation_map = {
        '，': ', ', ',': ', ',
        '。': '. ', '．': '. ',
        '！': '! ', '!': '! ',
        '？': '? ', '?': '? ',
        '；': '; ', ';': '; ',
        '、': ', '
    }

    for part in parts:
        if part in punctuation_map:
            pending_punct = punctuation_map[part]
        else:
            raw = translate_clause(part, glossary)
            if raw:
                if translated_parts and pending_punct:
                    translated_parts.append(pending_punct)
                    pending_punct = ''
                translated_parts.append(raw)

    result = ''.join(translated_parts)
    return postprocess(result)


def generate_cover_image(title, author, output_path):
    """
    Creates a simple elegant book cover image.
    """
    width, height = 600, 800
    image = Image.new("RGB", (width, height), "#1a1a1a")
    draw = ImageDraw.Draw(image)
    
    # Draw simple border
    draw.rectangle([20, 20, width-20, height-20], outline="#007acc", width=3)
    
    # Try using system font, fallback to default
    try:
        font_title = ImageFont.load_default()
        font_author = ImageFont.load_default()
    except IOError:
        font_title = ImageFont.load_default()
        font_author = ImageFont.load_default()

    draw.text((width//2, height//3), title, fill="#ffffff", font=font_title, anchor="mm")
    draw.text((width//2, height//2), f"Tác giả: {author}", fill="#cccccc", font=font_author, anchor="mm")
    draw.text((width//2, height - 100), "Dịch bằng MarianMT Cục Bộ", fill="#888888", font=font_author, anchor="mm")
    
    image.save(output_path, "JPEG")


class AppGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MarianMT Novel Translator & EPUB Packager")
        self.geometry("950x650")
        self.configure(bg=BG_COLOR)
        
        self.log_queue = queue.Queue()
        self.is_running = False
        self.abort_requested = False
        
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
        style.configure("TProgressbar", thickness=15)
        
        # Buttons
        style.configure("Primary.TButton", background=ACCENT_COLOR, foreground="#ffffff", font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#005999")])
        style.configure("Stop.TButton", background="#c62828", foreground="#ffffff", font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Stop.TButton", background=[("active", "#b71c1c")])

    def create_widgets(self):
        # Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Tab 1: Config
        self.tab_config = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_config, text="Cấu hình")
        
        # Tab 2: Logs
        self.tab_logs = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_logs, text="Tiến trình")
        
        self.setup_tab_config()
        self.setup_tab_logs()

    def setup_tab_config(self):
        # Master grid layout
        self.tab_config.columnconfigure(0, weight=1)
        self.tab_config.columnconfigure(1, weight=1)
        self.tab_config.rowconfigure(0, weight=1)
        
        # Left frame (Config entries)
        left_frame = ttk.Frame(self.tab_config, padding=20)
        left_frame.grid(row=0, column=0, sticky="nsew")
        
        # Title Label
        title_lbl = ttk.Label(left_frame, text="Tự động hóa: Cào → Dịch → EPUB (Mobile)", style="Header.TLabel")
        title_lbl.pack(anchor="w", pady=(0, 20))
        
        # URL field
        ttk.Label(left_frame, text="URL chương 1 (ví dụ: wa01.com/..._1.html):").pack(anchor="w", pady=2)
        self.ent_url = ttk.Entry(left_frame, width=70)
        self.ent_url.pack(fill="x", pady=(0, 10))
        self.ent_url.insert(0, "https://www.wa01.com/novel/pagea/disanchongrenge-changshuxin_1.html")
        
        # Novel Title
        ttk.Label(left_frame, text="Tên Truyện (EPUB Metadata):").pack(anchor="w", pady=2)
        self.ent_title = ttk.Entry(left_frame, width=70)
        self.ent_title.pack(fill="x", pady=(0, 10))
        self.ent_title.insert(0, "Đệ Tam Trùng Nhân Cách")
        
        # Author
        ttk.Label(left_frame, text="Tác giả:").pack(anchor="w", pady=2)
        self.ent_author = ttk.Entry(left_frame, width=70)
        self.ent_author.pack(fill="x", pady=(0, 10))
        self.ent_author.insert(0, "Thường Thư Hân")
        
        # Save Dir
        ttk.Label(left_frame, text="Thư mục lưu file EPUB:").pack(anchor="w", pady=2)
        dir_frame = ttk.Frame(left_frame)
        dir_frame.pack(fill="x", pady=(0, 20))
        
        self.ent_dir = ttk.Entry(dir_frame)
        self.ent_dir.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.ent_dir.insert(0, os.path.abspath("."))
        
        btn_browse = ttk.Button(dir_frame, text="Chọn thư mục...", command=self.browse_dir)
        btn_browse.pack(side="right")
        
        # Action Button
        self.btn_start = ttk.Button(left_frame, text="Bắt đầu Quy trình", style="Primary.TButton", command=self.start_process)
        self.btn_start.pack(pady=10, ipadx=20, ipady=5)
        
        # Right frame (Glossary / Character Name Dictionary)
        right_frame = ttk.Frame(self.tab_config, padding=20)
        right_frame.grid(row=0, column=1, sticky="nsew")
        
        ttk.Label(right_frame, text="Từ điển nhân vật & Thuật ngữ (Glossary):", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(right_frame, text="Định dạng: Tên_Tiếng_Trung: Tên_Tiếng_Việt (mỗi dòng 1 từ)\nGiúp triệt tiêu lỗi dịch nghĩa đen của tên riêng (VD: Vương Bát Hỉ thành tám niềm vui).", font=("Segoe UI", 9, "italic"), foreground=TEXT_MUTED).pack(anchor="w", pady=(0, 5))
        
        self.txt_glossary = tk.Text(right_frame, bg="#252526", fg=TEXT_COLOR, font=("Consolas", 10), wrap="none")
        self.txt_glossary.pack(fill="both", expand=True)
        
        # Insert defaults
        default_glossary = (
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
        self.txt_glossary.insert(tk.END, default_glossary)

    def setup_tab_logs(self):
        frame = ttk.Frame(self.tab_logs, padding=10)
        frame.pack(fill="both", expand=True)
        
        # Progress Bar & Labels
        self.lbl_status = ttk.Label(frame, text="Trạng thái: Đang chờ...", font=("Segoe UI", 10, "italic"))
        self.lbl_status.pack(anchor="w", pady=2)
        
        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 10))
        
        # Log Text Box
        self.txt_log = tk.Text(frame, bg="#121212", fg="#00ff00", font=("Consolas", 9), wrap="word")
        self.txt_log.pack(fill="both", expand=True, pady=(0, 10))
        
        # Controls Frame
        ctrl_frame = ttk.Frame(frame)
        ctrl_frame.pack(fill="x")
        
        self.btn_stop = ttk.Button(ctrl_frame, text="Dừng tiến trình", style="Stop.TButton", command=self.stop_process, state="disabled")
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
        
        self.is_running = True
        self.abort_requested = False
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.txt_log.delete(1.0, tk.END)
        
        # Switch to logs tab
        self.notebook.select(1)
        
        # Retrieve input data
        url = self.ent_url.get().strip()
        title = self.ent_title.get().strip()
        author = self.ent_author.get().strip()
        save_dir = self.ent_dir.get().strip()
        
        # Parse glossary
        glossary = {}
        glossary_raw = self.txt_glossary.get(1.0, tk.END)
        for line in glossary_raw.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            parts = line.split(':', 1)
            zh_key = parts[0].strip()
            vi_val = parts[1].strip()
            if zh_key and vi_val:
                glossary[zh_key] = vi_val
                
        # Run process in background thread
        threading.Thread(target=self.run_pipeline, args=(url, title, author, save_dir, glossary), daemon=True).start()

    def stop_process(self):
        if not self.is_running:
            return
        self.abort_requested = True
        self.log("\n[ABORT] Đang yêu cầu dừng tiến trình... Xin vui lòng đợi.")
        self.btn_stop.config(state="disabled")

    def run_pipeline(self, start_url, novel_title, author, save_dir, glossary):
        try:
            self.lbl_status.config(text="Bước 1/3: Đang phân tích và cào nội dung...")
            self.progress["value"] = 0
            
            # Detect pattern
            # Expected format: disanchongrenge-changshuxin_1.html
            match = re.match(r"(.*_)(\d+)(\.html)$", start_url)
            if not match:
                self.log("[Error] URL không hợp lệ! Vui lòng sử dụng URL kết thúc bằng _[N].html")
                self.finish_ui()
                return
            
            base_url = match.group(1)
            suffix = match.group(3)
            current_idx = int(match.group(2))
            
            self.log(f"Base URL: {base_url} (starting from index {current_idx})")
            self.log(f"Đã nạp {len(glossary)} từ khóa từ điển nhân vật.")
            
            chapters_data = []
            consecutive_errors = 0
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            # Step 1: Scrape all chapters sequentially
            while not self.abort_requested:
                url = f"{base_url}{current_idx}{suffix}"
                self.log(f"Cào chương {current_idx}: {url}...")
                
                try:
                    res = requests.get(url, headers=headers, timeout=15)
                    if res.status_code == 404:
                        self.log(f"Gặp mã lỗi 404 (Hết truyện hoặc link sai). Đã cào xong {len(chapters_data)} chương.")
                        break
                    
                    res.raise_for_status()
                    soup = BeautifulSoup(res.content, 'html.parser')
                    
                    title_div = soup.find('div', class_='title')
                    ch_title = title_div.get_text(strip=True) if title_div else f"Chương {current_idx}"
                    
                    content_div = soup.find('div', class_='content')
                    if not content_div:
                        self.log(f"Lỗi: Không tìm thấy nội dung chương {current_idx}. Bỏ qua.")
                        break
                    
                    # Remove unwanted tags
                    bookmark_link = content_div.find('a', class_='anchor_bookmark')
                    if bookmark_link:
                        bookmark_link.decompose()
                    for div in content_div.find_all('div', class_='mobadsq'):
                        div.decompose()
                        
                    paragraphs = []
                    p_tags = content_div.find_all('p')
                    for p in p_tags:
                        text = p.get_text(strip=True)
                        if text:
                            paragraphs.append(text)
                            
                    if not paragraphs:
                        text_content = content_div.get_text(separator="\n", strip=True)
                        paragraphs = [line.strip() for line in text_content.split("\n") if line.strip()]
                    
                    chapters_data.append({
                        'title_zh': ch_title,
                        'paragraphs_zh': paragraphs
                    })
                    
                    self.log(f"--> Đã lưu trữ chương {current_idx}: {ch_title} ({len(paragraphs)} đoạn văn)")
                    consecutive_errors = 0
                    current_idx += 1
                    time.sleep(1.0) # Respectful delay
                    
                except Exception as e:
                    self.log(f"Lỗi mạng khi cào chương {current_idx}: {e}")
                    consecutive_errors += 1
                    if consecutive_errors > 3:
                        self.log("Quá nhiều lỗi mạng liên tiếp. Dừng cào.")
                        break
                    time.sleep(3)
            
            if self.abort_requested:
                self.log("[Canceled] Tiến trình bị hủy bởi người dùng.")
                self.finish_ui()
                return
                
            if not chapters_data:
                self.log("[Warning] Không cào được chương nào! Quy trình kết thúc.")
                self.finish_ui()
                return

            # Step 2: Translate chapters
            self.lbl_status.config(text="Bước 2/3: Đang dịch qua mô hình MarianMT cục bộ...")
            self.progress["maximum"] = len(chapters_data)
            
            translated_chapters = []
            
            for index, ch in enumerate(chapters_data, 1):
                if self.abort_requested:
                    self.log("[Canceled] Tiến trình bị hủy bởi người dùng.")
                    self.finish_ui()
                    return
                
                zh_title = ch['title_zh']
                self.log(f"Đang dịch chương {index}/{len(chapters_data)}: {zh_title}")
                
                # Use sequential chapter number as title
                vi_title = f"Chương {index}"
                vi_paragraphs = []
                
                # Translate paragraphs in parallel
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(translate_paragraph, p, glossary) for p in ch['paragraphs_zh']]
                    for fut in futures:
                        if self.abort_requested:
                            break
                        vi_p = fut.result()
                        if vi_p:
                            vi_paragraphs.append(vi_p)
                
                translated_chapters.append({
                    'title': vi_title if vi_title else zh_title,
                    'paragraphs': vi_paragraphs
                })
                
                self.progress["value"] = index
                self.log(f"--> Hoàn thành dịch: {vi_title}")

            if self.abort_requested:
                self.finish_ui()
                return

            # Step 3: Build EPUB
            self.lbl_status.config(text="Bước 3/3: Đóng gói sách EPUB cho điện thoại...")
            epub_path = os.path.join(save_dir, f"{novel_title}.epub")
            
            book = epub.EpubBook()
            book.set_identifier(f"marianmt-translation-{int(time.time())}")
            book.set_title(novel_title)
            book.set_language("vi")
            book.add_author(author)
            
            # Create cover image
            cover_img_path = os.path.join(save_dir, "cover.jpg")
            generate_cover_image(novel_title, author, cover_img_path)
            
            with open(cover_img_path, 'rb') as f:
                book.set_cover("cover.jpg", f.read())
            
            # CSS for mobile optimization
            epub_css = """
            body {
                font-family: "Noto Serif", "Georgia", serif;
                font-size: 1.15em;
                line-height: 1.8;
                margin: 1.5em 1.0em;
                background-color: #ffffff;
                color: #111111;
            }
            h1, h2 {
                text-align: center;
                font-size: 1.5em;
                margin-bottom: 1.2em;
                color: #007acc;
            }
            p {
                text-indent: 1.5em;
                margin: 0.6em 0;
                text-align: justify;
            }
            """
            
            style_item = epub.EpubItem(
                uid="style_pub",
                file_name="style/epub.css",
                media_type="text/css",
                content=epub_css
            )
            book.add_item(style_item)
            
            # Add chapters to EPUB
            epub_chapters = []
            for idx, ch in enumerate(translated_chapters, 1):
                html_filename = f"chap_{idx:03d}.xhtml"
                
                # HTML content
                paragraphs_html = "".join([f"<p>{p}</p>" for p in ch['paragraphs']])
                content_html = f"""
                <?xml version="1.0" encoding="utf-8"?>
                <!DOCTYPE html>
                <html xmlns="http://www.w3.org/1999/xhtml">
                <head>
                    <title>{ch['title']}</title>
                    <link rel="stylesheet" href="style/epub.css" type="text/css"/>
                </head>
                <body>
                    <h1>{ch['title']}</h1>
                    {paragraphs_html}
                </body>
                </html>
                """
                
                epub_ch = epub.EpubHtml(
                    title=ch['title'],
                    file_name=html_filename,
                    lang='vi'
                )
                epub_ch.content = content_html
                epub_ch.add_item(style_item)
                
                book.add_item(epub_ch)
                epub_chapters.append(epub_ch)
                
            book.toc = tuple([epub.Link(c.file_name, c.title, c.file_name) for c in epub_chapters])
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            
            # Build spine
            book.spine = ['nav'] + epub_chapters
            
            # Write EPUB file
            epub.write_epub(epub_path, book, {})
            
            try:
                from build_epub import copy_to_downloads
                dl_path = copy_to_downloads(epub_path)
                if dl_path:
                    self.log(f"\n[CLONE] Đã sao chép một bản sang thư mục Download: {dl_path}")
            except Exception as dl_err:
                self.log(f"\n[WARNING] Không thể sao chép sang thư mục Download: {dl_err}")
            
            # Clean up temporary cover image
            if os.path.exists(cover_img_path):
                os.remove(cover_img_path)
                
            self.log(f"\n[THÀNH CÔNG] Đã lưu sách điện tử EPUB tại: {epub_path}")
            self.lbl_status.config(text="Đã hoàn thành xuất file EPUB!")
            messagebox.showinfo("Thành công", f"Đã dịch và đóng gói xong file EPUB tại:\n{epub_path}")
            
        except Exception as ex:
            self.log(f"\n[ERROR] Lỗi hệ thống: {ex}")
            messagebox.showerror("Lỗi", f"Có lỗi xảy ra: {ex}")
            
        finally:
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
