import json
import sys

JSON_PATH = r"d:\MingggSync\Playground\Podcast_Tools\00Outputfiles\Joe_Rogan_Experience_2054_-_Elon_Musk\Joe_Rogan_Experience_2054_-_Elon_Musk.json"

def inspect():
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    segments = data.get('segments', [])
    total = len(segments)
    print(f"Total Segments: {total}")
    
    print(f"Version: {data.get('version')}")
    print(f"Polished Timestamp: {data.get('polished_timestamp')}")
    
    indices = [0, 950, 2000]
    for idx in indices:
        if idx < total:
            print(f"\n--- Segment {idx} ---")
            print(f"Speaker: {segments[idx].get('speaker')}")
            print(f"EN: {segments[idx].get('originalEnglish')}")
            print(f"CN: {segments[idx].get('translatedChinese')}")
            print(f"Keys: {list(segments[idx].keys())}")

if __name__ == "__main__":
    inspect()
