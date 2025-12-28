
import json
import os
import sys

# Try to import opencc
try:
    from opencc import OpenCC
except ImportError:
    print("opencc-python-reimplemented not found.")
    sys.exit(1)

def is_traditional(text):
    cc = OpenCC('t2s')
    converted = cc.convert(text)
    return text != converted

def check_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    trad_segments = []
    for i, seg in enumerate(data.get('segments', [])):
        text = seg.get('translatedChinese', '')
        if is_traditional(text):
            trad_segments.append((i, text))
    return trad_segments

def check_txt(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    trad_lines = []
    for i, line in enumerate(lines):
        if 'CN:' in line:
            text = line.split('CN:')[1].strip()
            if is_traditional(text):
                trad_lines.append((i, text))
    return trad_lines

if __name__ == "__main__":
    json_path = r"d:\MingggSync\Playground\Podcast_Tools\Google： The AI Company. Google is amazingly well-positioned... will they win in AI？ (audio).json"
    txt_path = r"d:\MingggSync\Playground\Podcast_Tools\Google： The AI Company. Google is amazingly well-positioned... will they win in AI？ (audio).txt"
    
    if os.path.exists(json_path):
        json_results = check_json(json_path)
        print(f"JSON: {len(json_results)} traditional segments.")
        if json_results:
            for i, text in json_results[:3]:
                print(f"  Seg {i}: {text}")
    
    if os.path.exists(txt_path):
        txt_results = check_txt(txt_path)
        print(f"TXT: {len(txt_results)} traditional segments.")
        if txt_results:
            for i, text in txt_results[:3]:
                print(f"  Line {i+1}: {text}")
