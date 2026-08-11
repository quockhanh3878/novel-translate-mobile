#!/data/data/com.termux/files/usr/bin/bash
# update_termux.sh - Cap nhat code moi nhat va khoi dong lai Web GUI

DEST="$HOME/novel"
cd "$DEST"

echo "== 1/3: Dung tien trinh cu =="
pkill -f web_gui.py || true
sleep 1

echo "== 2/3: Cap nhat code moi nhat =="
git fetch origin
git reset --hard origin/main
pip install -r requirements.txt

echo "== 3/3: Khoi dong lai Web GUI =="
nohup python web_gui.py > web_gui.log 2>&1 &
sleep 2
termux-open-url http://localhost:8000

echo "Da cap nhat thanh cong!"
