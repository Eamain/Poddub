
import json
import os
import sys

# Try to import opencc, or use a simple replacement if not found
try:
    from opencc import OpenCC
except ImportError:
    print("opencc-python-reimplemented not found. Please install it with: pip install opencc-python-reimplemented")
    sys.exit(1)

def convert_json(input_path):
    cc = OpenCC('t2s') # traditional to simplified
    if not os.path.exists(input_path):
        return
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'segments' in data:
        for seg in data['segments']:
            if 'translatedChinese' in seg:
                seg['translatedChinese'] = cc.convert(seg['translatedChinese'])
    if 'detectedSpeakers' in data:
        data['detectedSpeakers'] = [cc.convert(s) for s in data['detectedSpeakers']]
    with open(input_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Successfully converted {input_path} to Simplified Chinese.")

def convert_txt(input_path):
    cc = OpenCC('t2s')
    if not os.path.exists(input_path):
        return
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    converted = cc.convert(content)
    with open(input_path, 'w', encoding='utf-8') as f:
        f.write(converted)
    print(f"Successfully converted {input_path} to Simplified Chinese.")

if __name__ == "__main__":
    base_file = r"d:\MingggSync\Playground\Podcast_Tools\Google： The AI Company. Google is amazingly well-positioned... will they win in AI？ (audio)"
    convert_json(base_file + ".json")
    convert_txt(base_file + ".txt")
