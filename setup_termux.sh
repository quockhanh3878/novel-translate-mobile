#!/data/data/com.termux/files/usr/bin/bash
# setup_termux.sh - Chay 1 LAN DUY NHAT sau khi cai Termux, lo het phan con lai: cai
# python/git, tai code, hoi API key, cap quyen luu EPUB/PDF ra bo nho may, cau hinh mo GUI
# web tu dong moi lan mo Termux. Sau buoc nay nguoi dung khong can dung dong lenh nao
# nua - chi mo Termux la vao thang trang web dich truyen.
set -euo pipefail
REPO_URL="https://github.com/quockhanh3878/novel-translate-mobile"
DEST="$HOME/novel"

require_termux_api() {
    if ! command -v termux-wake-lock >/dev/null 2>&1; then
        echo "LOI: Thieu goi termux-api. Hay chay lai script nay."
        return 1
    fi
    if ! termux-wake-lock; then
        echo "LOI: Chua dung duoc Termux:API. Hay cai app Termux:API cung nguon voi app Termux (F-Droid hoac GitHub), mo app mot lan va cap quyen can thiet."
        return 1
    fi
    termux-wake-unlock || true
}

require_shared_storage() {
    local shared_dir="$HOME/storage/shared"
    local check_file="$shared_dir/.novel-translator-storage-check-$$"
    if [ ! -L "$shared_dir" ] || [ ! -d "$shared_dir" ]; then
        echo "LOI: Chua cap quyen bo nho Android. Hay chon Allow khi Termux hoi quyen, sau do chay lai script."
        return 1
    fi
    if ! touch "$check_file" || ! rm -f "$check_file"; then
        echo "LOI: Khong ghi duoc vao bo nho dung chung cua Android. Hay kiem tra quyen Files and media cua Termux."
        return 1
    fi
}

start_gui() {
    nohup python web_gui.py > web_gui.log 2>&1 &
    local gui_pid=$!
    local attempt
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        if ! kill -0 "$gui_pid" 2>/dev/null; then
            echo "LOI: GUI khong khoi dong. Xem 20 dong cuoi trong $DEST/web_gui.log:"
            tail -n 20 web_gui.log || true
            return 1
        fi
        if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=1).read(1)" >/dev/null 2>&1; then
            termux-open-url http://localhost:8000
            return 0
        fi
        sleep 1
    done
    echo "LOI: GUI chua san sang sau 10 giay. Xem $DEST/web_gui.log."
    return 1
}

echo "== 1/5: Cai python, git, termux-api, pillow, lxml =="
pkg update -y && pkg install -y python git termux-api python-pillow python-lxml
# python-pillow da co san tu kho Termux, khong can compile tu source
require_termux_api

echo "== 2/5: Tai code =="
if [ -d "$DEST/.git" ]; then
    cd "$DEST"
    git fetch origin
    git reset --hard origin/main
else
    git clone "$REPO_URL" "$DEST"
fi
cd "$DEST"
chmod +x run_termux.sh update_termux.sh 2>/dev/null || true
pip install --break-system-packages -r requirements.txt 2>/dev/null || pip install -r requirements.txt
pip install --break-system-packages --only-binary=:all: curl_cffi 2>/dev/null || pip install --only-binary=:all: curl_cffi 2>/dev/null || true

echo "== 3/5: DeepSeek API key =="
if [ ! -f .env ]; then
    echo -n "Dan API key DeepSeek (sk-...): "
    read -r APIKEY
    echo "DEEPSEEK_API_KEY=$APIKEY" > .env
else
    echo "Da co .env, bo qua."
fi

echo "== 4/5: Cap quyen luu EPUB/PDF ra bo nho may (se hien popup xin quyen) =="
termux-setup-storage
sleep 2
require_shared_storage

echo "== 5/5: Tu dong mo GUI web moi lan mo Termux =="
if ! grep -q web_gui.py "$HOME/.bashrc" 2>/dev/null; then
    cat >> "$HOME/.bashrc" <<EOF
if ! pgrep -f web_gui.py > /dev/null; then
    cd "$DEST" && nohup python web_gui.py > web_gui.log 2>&1 &
    sleep 1
    termux-open-url http://localhost:8000
fi
EOF
fi

echo ""
echo "Xong! Dong Termux roi mo lai la tu dong vao trang dich truyen."
cd "$DEST"
start_gui
