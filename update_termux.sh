#!/data/data/com.termux/files/usr/bin/bash
# update_termux.sh - Cap nhat code moi nhat va khoi dong lai Web GUI
set -euo pipefail

DEST="$HOME/novel"
cd "$DEST"

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

echo "== 1/3: Dung tien trinh cu =="
pkill -f web_gui.py || true
sleep 1

echo "== 2/3: Cap nhat code moi nhat =="
git fetch origin
git reset --hard origin/main
chmod +x run_termux.sh update_termux.sh setup_termux.sh 2>/dev/null || true
pip install --break-system-packages -r requirements.txt 2>/dev/null || pip install -r requirements.txt
pip install --break-system-packages --only-binary=:all: curl_cffi 2>/dev/null || pip install --only-binary=:all: curl_cffi 2>/dev/null || true

echo "== 3/3: Khoi dong lai Web GUI =="
start_gui

echo "Da cap nhat thanh cong!"
