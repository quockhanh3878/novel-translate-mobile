#!/data/data/com.termux/files/usr/bin/bash
# run_termux.sh - Widget "app": cham icon tren man hinh chinh, nhap URL (tu cao) HOAC
# duong dan file da cao san + ten truyen, chay pipeline.py (cao neu can -> dich DeepSeek
# API -> dong goi EPUB) ngam, bao ket qua qua thong bao. Can Termux + Termux:API +
# Termux:Widget (F-Droid) cho trai nghiem 1-cham; khong co widget van chay tay duoc:
# ./run_termux.sh "<start-url-hoac-duong-dan-file-tho>" "<Ten truyen>"
set -e
cd "$(dirname "$0")"

if [ -n "$1" ]; then
    INPUT="$1"; TITLE="${2:-}"
else
    INPUT=$(termux-dialog text -t "URL chuong 1 (hoac duong dan file da cao san)" | python3 -c "import json,sys;print(json.load(sys.stdin).get('text',''))" 2>/dev/null || true)
    TITLE=$(termux-dialog text -t "Ten truyen (de trong se tu doan)" | python3 -c "import json,sys;print(json.load(sys.stdin).get('text',''))" 2>/dev/null || true)
fi

[ -z "$INPUT" ] && { echo "Thieu URL hoac file tho."; exit 1; }

if [ -z "$TITLE" ]; then
    TITLE=$(INPUT="$INPUT" python3 -c 'import os; from crawler import guess_title; print(guess_title(os.environ["INPUT"]))' 2>/dev/null || echo "Truyen")
fi

case "$INPUT" in
    http*) PIPE_ARGS=(--start-url "$INPUT") ;;
    *)     PIPE_ARGS=(--raw "$INPUT") ;;
esac

termux-wake-lock
LOG_FILE="pipeline.log"
if python pipeline.py "${PIPE_ARGS[@]}" --title "$TITLE" > "$LOG_FILE" 2>&1; then
    STATUS=0
else
    STATUS=$?
fi
termux-wake-unlock

if [ $STATUS -eq 0 ]; then
    termux-notification -t "Xong: $TITLE" -c "EPUB da san sang: ${TITLE}.epub"
else
    termux-notification -t "Loi: $TITLE" -c "Xem $LOG_FILE"
fi
