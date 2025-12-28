
import os
import json
import argparse
from pathlib import Path
from google import genai
from google.genai import types

# Configuration
MODEL_ID = "gemini-2.5-flash"

def load_api_key():
    """Attempts to find .env.local and load GEMINI_API_KEY."""
    current_dir = Path(__file__).resolve().parent
    candidates = [
        current_dir / ".env.local",
        current_dir.parent / ".env.local",
        current_dir.parent / "Poddub_Minimax" / "codes" / ".env.local",
        current_dir.parent.parent / "poddub-ai" / "server" / ".env.local", 
    ]
    for env_path in candidates:
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return None

def generate_outline(json_path, output_dir):
    api_key = load_api_key()
    if not api_key:
        print("Error: No GEMINI_API_KEY found.")
        return

    client = genai.Client(api_key=api_key)
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data.get("segments", [])
    if not segments:
        print("Error: No segments found in JSON.")
        return

    # Prepare transcript for context (simplify to minimize token usage if needed, but 2.5 Flash is huge)
    # We will format it as: [Time] Speaker: Text
    transcript_text = ""
    for seg in segments:
        start = seg.get('startTime', '')
        speaker = seg.get('speaker', 'Unknown')
        text = seg.get('translatedChinese', '') # Use Chinese translation for summary
        if not text:
             text = seg.get('originalEnglish', '')
        transcript_text += f"[{start}] {speaker}: {text}\n"

    print(f"Transcript length: {len(transcript_text)} chars. Sending to Gemini for outlining...")

    prompt = """
    You are a professional Podcast Editor.
    Your task is to summarize the attached podcast transcript into a structured Markdown outline.

    **Reference Style**:
    The output must strictly follow the format below (Do not leave out any section):

    # {Catchy Title for the Episode}

    本期内容转录自英文播客《In Good Company》同名剧集。文章开头的音频是中文。文末的音频是英文原声。中间正文部分对整个播客的内容做了分段介绍。

    {Podcast Name} 是一档专门讲述...的深度播客。今天这一集。我们要聊的主角是 {Main Topic/Guest}。你可能知道...。但你可能不知道：

    *   {Bullet Point 1: Key insight or surprising fact from the episode}
    *   {Bullet Point 2: Another key insight}
    *   {Bullet Point 3: Another key insight}

    这一集。我们将带你... {Brief transition into the main content}.

    免责声明 (Disclaimer)：
    本节目内容是对知名英文播客的中文转译。音标内容由 AI 技术根据原英文内容进行翻译、重组并生成语音。旨在促进中文社区的学习与交流。
    *   原始内容版权归原播客所有。
    *   AI 翻译可能存在误差。部分专业术语或语境可能与原意略有出入。请以英文原版为准。
    *   本节目不构成任何投资建议。

    ---

    ### 第一章：{Chapter Title with Chinese Numbering}

    [{Start Time} - {End Time}]
    {Detailed summary of this chapter. Use paragraphs, not bullet points. Focus on the narrative flow.}

    ### 第二章：{Chapter Title}

    [{Start Time} - {End Time}]
    {Summary...}

    ...

    ### 终章：{Chapter Title}

    [{Start Time} - {End Time}]
    {Conclusion and Outlook}

    **Requirements**:
    1. **Language**: SIMPLIFIED CHINESE (Simplified Chinese).
    2. **Structure**: Divide the content into logical chapters (4-8 chapters).
    3. **Timestamps**: accurate start and end times based on the transcript provided.
    4. **Tone**: Professional, engaging, storytelling style (magazine/newsletter style).
    5. **Headings**: Use "第一章：", "第二章：" etc. for chapter titles.
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_text(text=f"TRANSCRIPT DATA:\n{transcript_text}")
            ]
        )
        
        outline_content = response.text
        
        # Extract title for filename
        import re
        title_match = re.search(r'^#\s*(.+)', outline_content)
        if title_match:
            # Sanitize for Windows filename
            raw_title = title_match.group(1).strip()
            safe_title = re.sub(r'[<>:"/\\|?*]', '', raw_title)
            output_filename = f"{safe_title}.md"
        else:
            base_name = Path(json_path).stem
            output_filename = f"{base_name}_Outline.md"

        # Save
        output_path = Path(output_dir) / output_filename
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(outline_content)
            
        print(f"✅ Outline generated: {output_path}")
        return output_path

    except Exception as e:
        print(f"❌ Custom Outline Generation Failed: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Input JSON transcript file")
    parser.add_argument("--outdir", help="Output directory", default=None)
    args = parser.parse_args()
    
    fpath = Path(args.file)
    outdir = args.outdir if args.outdir else fpath.parent
    
    generate_outline(fpath, outdir)
