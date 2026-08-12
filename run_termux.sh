#!/data/data/com.termux/files/usr/bin/bash
# run_termux.sh - Widget "app": cham icon tren man hinh chinh, nhap URL (tu cao) HOAC
# duong dan file da cao san + ten truyen, chay pipeline.py (cao neu can -> dich DeepSeek
# API -> dong goi EPUB va/hoac PDF) ngam, bao ket qua qua thong bao. Can Termux +
# Termux:API + Termux:Widget (F-Droid) cho trai nghiem 1-cham; khong co widget van
# chay tay duoc:
#   ./run_termux.sh "<start-url-hoac-duong-dan-file-tho>" "<Ten truyen>" [epub|pdf|both]
# Mac dinh la 'epub'. Chon 'pdf' khi may khong co reader EPUB, hoac 'both' de co ca hai.
# pipeline.py tu di chuyen san pham vao ~/storage/shared/Documents/DichTruyen (path
# hop le voi Android Scoped Storage API 30+) va kich hoat MediaStore quet lai file
# neu Termux:API co san.
set -e
cd "$(dirname "$0")"

if [ -n "$1" ] && [ -n "$2" ]; then
    INPUT="$1"; TITLE="$2"; FORMATS="${3:-epub}"
else
    INPUT=$(termux-dialog text -t "URL chuong 1 (hoac duong dan file da cao san)" | python3 -c "import json,sys;print(json.load(sys.stdin).get('text',''))")
    TITLE=$(termux-dialog text -t "Ten truyen" | python3 -c "import json,sys;print(json.load(sys.stdin).get('text',''))")
    FMT_IDX=$(termux-dialog sheet -t "Dinh dang xuat" -v "epub,pdf,both" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin).get('text','epub'))" || echo "epub")
    FORMATS="${FMT_IDX:-epub}"
fi

[ -z "$INPUT" ] || [ -z "$TITLE" ] && { echo "Thieu URL/file hoac ten truyen."; exit 1; }
case "$FORMATS" in
    epub|pdf|both) ;;
    *) FORMATS="epub" ;;
esac

case "$INPUT" in
    http*) PIPE_ARGS=(--start-url "$INPUT") ;;
    *)     PIPE_ARGS=(--raw "$INPUT") ;;
esac

termux-wake-lock
python pipeline.py "${PIPE_ARGS[@]}" --title "$TITLE" --formats "$FORMATS" --to-documents > "pipeline_${TITLE}.log" 2>&1
STATUS=$?
termux-wake-unlock

if [ $STATUS -eq 0 ]; then
    SAVED=$(grep '^\[LUU\]' "pipeline_${TITLE}.log" | sed 's/^\[LUU\] //' | tr '\n' ' ')
    termux-notification -t "Xong: $TITLE" -c "Da luu: ${SAVED:-$TITLE}"
else
    termux-notification -t "Loi: $TITLE" -c "Xem pipeline_${TITLE}.log"
fi
