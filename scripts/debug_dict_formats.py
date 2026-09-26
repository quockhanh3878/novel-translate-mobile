"""Debug script - inspect data formats from cloned repos."""
import io
import json
import sys

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except (AttributeError, OSError):
        pass

SRC = r"C:\Users\quock\AppData\Local\Temp\opencode\dict-sources"

print("=" * 70)
print("1. CVDICT.u8 - format check")
print("=" * 70)
with open(fr"{SRC}\CVDICT\CVDICT.u8", "r", encoding="utf-8") as f:
    count = 0
    for line in f:
        if line.startswith("#"):
            continue
        if line.strip():
            count += 1
            if count <= 5:
                print(f"  [{count}] {repr(line.rstrip()[:120])}")
    print(f"  Total non-comment lines: {count}")

print("\n" + "=" * 70)
print("2. cvdict_full.json - format check")
print("=" * 70)
with open(fr"{SRC}\chugiai-zh-en-vi\cvdict_full.json", "r", encoding="utf-8") as f:
    data = json.load(f)
print(f"  Type: {type(data).__name__}")
if isinstance(data, dict):
    print(f"  Total keys: {len(data)}")
    keys = list(data.keys())[:3]
    for k in keys:
        v = data[k]
        print(f"\n  KEY: {repr(k)}")
        print(f"  VAL: {repr(v)[:300]}")
        if isinstance(v, list) and v:
            print(f"  First item type: {type(v[0]).__name__}")
            if isinstance(v[0], dict):
                print(f"  First item keys: {list(v[0].keys())}")
                print(f"  First item sample: {repr(v[0])[:400]}")

print("\n" + "=" * 70)
print("3. hanzi-sino-vietnamese/characters.json - format check")
print("=" * 70)
with open(fr"{SRC}\hanzi-sino-vietnamese\data\characters.json", "r", encoding="utf-8") as f:
    data2 = json.load(f)
print(f"  Type: {type(data2).__name__}, len: {len(data2)}")
print(f"  First entry: {json.dumps(data2[0], ensure_ascii=False, indent=2)}")
print(f"  Second entry: {json.dumps(data2[1], ensure_ascii=False, indent=2)}")

print("\n" + "=" * 70)
print("4. cedict_full.json - format check")
print("=" * 70)
with open(fr"{SRC}\chugiai-zh-en-vi\cedict_full.json", "r", encoding="utf-8") as f:
    data3 = json.load(f)
print(f"  Type: {type(data3).__name__}")
if isinstance(data3, dict):
    print(f"  Total keys: {len(data3)}")
    keys = list(data3.keys())[:3]
    for k in keys:
        v = data3[k]
        print(f"\n  KEY: {repr(k)}")
        print(f"  VAL: {repr(v)[:300]}")