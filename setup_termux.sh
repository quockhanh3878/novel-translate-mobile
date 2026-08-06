#!/data/data/com.termux/files/usr/bin/bash
# setup_termux.sh - Chay 1 LAN DUY NHAT sau khi cai Termux, lo het phan con lai: cai
# python/git, tai code, hoi API key, cap quyen luu EPUB ra bo nho may, cau hinh mo GUI
# web tu dong moi lan mo Termux. Sau buoc nay nguoi dung khong can dung dong lenh nao
# nua - chi mo Termux la vao thang trang web dich truyen.
set -e
REPO_URL="https://github.com/quockhanh3878/novel-translate-mobile"
DEST="$HOME/novel"

echo "== 1/5: Cai python, git, termux-api, pillow, lxml =="
pkg update -y && pkg install -y python git termux-api python-pillow python-lxml
# python-pillow da co san tu kho Termux, khong can compile tu source

echo "== 2/5: Tai code =="
if [ -d "$DEST/.git" ]; then
    cd "$DEST"
    git stash --include-untracked 2>/dev/null || true
    git pull --ff-only || git reset --hard origin/main
else
    git clone "$REPO_URL" "$DEST"
fi
cd "$DEST"
pip install -r requirements.txt

echo "== 3/5: DeepSeek API key =="
if [ ! -f .env ]; then
    echo -n "Dan API key DeepSeek (sk-...): "
    read -r APIKEY
    echo "DEEPSEEK_API_KEY=$APIKEY" > .env
else
    echo "Da co .env, bo qua."
fi

echo "== 4/5: Cap quyen luu EPUB ra bo nho may (se hien popup xin quyen) =="
termux-setup-storage
sleep 2

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
cd "$DEST" && nohup python web_gui.py > web_gui.log 2>&1 &
sleep 1
termux-open-url http://localhost:8000
