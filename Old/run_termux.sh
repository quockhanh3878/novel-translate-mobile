#!/data/data/com.termux/files/usr/bin/bash
# run_termux.sh - Widget "app": cham icon tren man hinh chinh, nhap URL (tu cao) HOAC
# duong dan file da cao san + ten truyen, chay pipeline.py (cao neu can -> dich DeepSeek
# API -> dong goi EPUB) ngam, bao ket qua qua thong bao. Can Termux + Termux:API +
# Termux:Widget (F-Droid) cho trai nghiem 1-cham; khong co widget van chay tay duoc:
# ./run_termux.sh "<start-url-hoac-duong-dan-file-tho>" "<Ten truyen>"
set -e
cd "$(dirname "$0")"

if [ -n "$1" ] && [ -n "$2" ]; then
    INPUT="$1"; TITLE="$2"
else
    INPUT=$(termux-dialog text -t "URL chuong 1 (hoac duong dan file da cao san)" | python3 -c "import json,sys;print(json.load(sys.stdin).get('text',''))")
    TITLE=$(termux-dialog text -t "Ten truyen" | python3 -c "import json,sys;print(json.load(sys.stdin).get('text',''))")
fi

[ -z "$INPUT" ] || [ -z "$TITLE" ] && { echo "Thieu URL/file hoac ten truyen."; exit 1; }

case "$INPUT" in
    http*) PIPE_ARGS=(--start-url "$INPUT") ;;
    *)     PIPE_ARGS=(--raw "$INPUT") ;;
esac

termux-wake-lock
python pipeline.py "${PIPE_ARGS[@]}" --title "$TITLE" > "pipeline_${TITLE}.log" 2>&1
STATUS=$?
termux-wake-unlock

if [ $STATUS -eq 0 ]; then
    termux-notification -t "Xong: $TITLE" -c "EPUB da san sang: ${TITLE}.epub"
else
    termux-notification -t "Loi: $TITLE" -c "Xem pipeline_${TITLE}.log"
fi
