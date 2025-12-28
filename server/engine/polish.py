
import os
import json
import argparse
import time
from pathlib import Path
from google import genai
from google.genai import types

# Configuration
MODEL_ID = "gemini-2.5-flash"
BATCH_SIZE = 100  # Process 100 segments at a time to maintain context but avoid huge payloads

def load_api_key():
    """Attempts to find .env.local and load GEMINI_API_KEY."""
    current_dir = Path(__file__).resolve().parent
    candidates = [
        current_dir / ".env.local",
        current_dir.parent / ".env.local",  # Look in root Podcast_Tools
        current_dir.parent / "Poddub_Minimax" / "codes" / ".env.local",
        Path("d:/MingggSync/Playground/poddub-ai/.env.local"),
    ]
    for env_path in candidates:
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return None

def polish_batch(client, batch_segments):
    """
    Sends a batch of segments to Gemini for polishing.
    """
    # Prepare input JSON for the model
    input_data = []
    for seg in batch_segments:
        input_data.append({
            "id": seg.get("startTime"), # Use startTime as ID
            "original_english": seg.get("originalEnglish", ""),
            "current_translation": seg.get("translatedChinese", ""),
            "speaker": seg.get("speaker", "Unknown")
        })

    prompt = """
    You are a professional Podcast Editor and Translator.
    Your task is to POLISH the Chinese translation of a podcast transcript to make it sound like a high-quality, natural Chinese podcast.

    **Instructions**:
    1.  **Refine the Tone**: Make it conversational, engaging, and "grounded" (接地气). Avoid stiff, machine-translated phrasing.
    2.  **Fix Grammar & Flow**: Ensure sentences flow smoothly. You can split or combine sentences if it improves the listening experience.
    3.  **Context Aware**: Use the 'original_english' to ensure accuracy, but prioritize the naturalness of the 'refined_translation'.
    4.  **Speaker consistency**: Maintain a consistent voice for each speaker.
    5.  **Keep Proper Nouns in English**: Do NOT translate names of people (e.g. Elon Musk, Joe Rogan), places, countries, or companies. Keep them in their original English form in the Chinese translation.

    **Input**: A JSON list of segments with `id`, `original_english`, and `current_translation`.
    **Output**: A JSON list of objects with `id` and `refined_translation`. ONLY return the JSON.
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_text(text=f"INPUT DATA:\n{json.dumps(input_data, ensure_ascii=False)}")
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    'type': 'ARRAY',
                    'items': {
                        'type': 'OBJECT',
                        'properties': {
                            'id': {'type': 'STRING'},
                            'refined_translation': {'type': 'STRING'}
                        },
                        'required': ['id', 'refined_translation']
                    }
                }
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ Batch generation failed: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Polish Podcast Transcript Translations")
    parser.add_argument("file", help="Input JSON transcript file")
    parser.add_argument("--save-copy", action="store_true", help="Save as _polished.json instead of overwriting (default: overwrite)")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    api_key = load_api_key()
    if not api_key:
        print("Error: No GEMINI_API_KEY found.")
        return

    client = genai.Client(api_key=api_key)

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data.get("segments", [])
    if not segments:
        print("No segments found.")
        return

    print(f"🚀 Starting Polishing for: {file_path.name}")
    print(f"Total Segments: {len(segments)}")

    # Process in batches
    polished_map = {}
    total_batches = (len(segments) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(segments), BATCH_SIZE):
        batch_idx = i // BATCH_SIZE + 1
        print(f"Processing Batch {batch_idx}/{total_batches}...", end="\r")
        
        batch = segments[i : i + BATCH_SIZE]
        result = polish_batch(client, batch)
        
        if result:
            for item in result:
                polished_map[item['id']] = item['refined_translation']
        
        time.sleep(1) # Prevent rate limiting

    print("\n✅ Polishing Complete. Applying changes...")

    # Apply updates
    updates_count = 0
    for seg in segments:
        seg_id = seg.get("startTime")
        if seg_id in polished_map:
            # simple check if changed
            if seg['translatedChinese'] != polished_map[seg_id]:
                seg['translatedChinese'] = polished_map[seg_id]
                updates_count += 1
    
    print(f"Updated {updates_count} segments.")

    # Mark version
    data["version"] = f"{data.get('version', 'unknown')}-polished"
    data["polished_timestamp"] = int(time.time() * 1000)

    # Save
    if args.save_copy:
        output_path = file_path.parent / f"{file_path.stem}_polished.json"
    else:
        output_path = file_path # Overwrite
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved to: {output_path}")

if __name__ == "__main__":
    main()
