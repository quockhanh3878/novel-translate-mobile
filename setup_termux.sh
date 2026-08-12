#!/data/data/com.termux/files/usr/bin/bash
# setup_termux.sh - Chay 1 LAN DUY NHAT sau khi cai Termux, lo het phan con lai: cai
# python/git, tai code, hoi API key, cap quyen luu EPUB/PDF ra bo nho may, cau hinh
# mo GUI web tu dong moi lan mo Termux. Sau buoc nay nguoi dung khong can dung dong
# lenh nao nua - chi mo Termux la vao thang trang web dich truyen.
set -e
REPO_URL="https://github.com/quockhanh3878/novel-translate-mobile"
DEST="$HOME/novel"

echo "== 1/6: Cai python, git, termux-api, pillow, lxml, fontconfig =="
# fontconfig keo theo dejavu-fonts-ttf (font TTF ho tro tieng Viet day du),
# can thiet cho build_pdf.py; pillow/lxml da co san binary tren kho Termux
# (khong can compile).
pkg update -y && pkg install -y python git termux-api python-pillow python-lxml fontconfig

echo "== 2/6: Tai code =="
if [ -d "$DEST/.git" ]; then
    cd "$DEST"
    git fetch origin
    git reset --hard origin/main
else
    git clone "$REPO_URL" "$DEST"
fi
cd "$DEST"
pip install -r requirements.txt

echo "== 3/6: DeepSeek API key =="
if [ ! -f .env ]; then
    echo -n "Dan API key DeepSeek (sk-...): "
    read -r APIKEY
    echo "DEEPSEEK_API_KEY=$APIKEY" > .env
else
    echo "Da co .env, bo qua."
fi

echo "== 4/6: Cap quyen luu EPUB/PDF ra bo nho may (se hien popup xin quyen) =="
# `termux-setup-storage` tao symlink ~/storage/shared -> /storage/emulated/0
# (public shared storage). Day la LOI DUY NHAT ghi vao thu muc user-visible tren
# Android API 30+ ma khong can MANAGE_EXTERNAL_STORAGE (Scoped Storage rules).
termux-setup-storage
sleep 2

# Tao san thu muc dich neu chua co (mot so may khong co san Documents/)
mkdir -p "$HOME/storage/shared/Documents/DichTruyen" 2>/dev/null || true

echo "== 5/6: Tu dong mo GUI web moi lan mo Termux =="
if ! grep -q web_gui.py "$HOME/.bashrc" 2>/dev/null; then
    cat >> "$HOME/.bashrc" <<EOF
if ! pgrep -f web_gui.py > /dev/null; then
    cd "$DEST" && nohup python web_gui.py > web_gui.log 2>&1 &
    sleep 1
    termux-open-url http://localhost:8000
fi
EOF
fi

echo "== 6/6: Khoi dong Web GUI =="
cd "$DEST" && nohup python web_gui.py > web_gui.log 2>&1 &
sleep 1
termux-open-url http://localhost:8000

echo ""
echo "Xong! Dong Termux roi mo lai la tu dong vao trang dich truyen."
echo "File EPUB/PDF se duoc luu vao Documents/DichTruyen tren bo nho may."
