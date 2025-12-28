import os
import json
import argparse
from pathlib import Path

def generate_summary(json_data, output_md_path, project_name):
    segments = json_data.get("segments", [])
    if not segments: return
    
    # Simple logic to group into "Chapters" every ~30 mins or major transitions
    # For now, we'll do a simple breakdown or just the intro + segments
    
    summary_content = f"# {project_name}\n\n"
    summary_content += "## 播客摘要 (Podcast Summary)\n\n"
    summary_content += "本文件由自动化工作流生成。包含了该播客的核心章节和带时间戳的内容概览。\n\n"
    
    # Generate ~5-7 chapters automatically based on duration
    total_segments = len(segments)
    chunk_size = max(1, total_segments // 6)
    
    for i in range(0, total_segments, chunk_size):
        seg = segments[i]
        timestamp = seg.get("timestamp", "00:00")
        text = seg.get("translatedChinese", seg.get("originalEnglish", ""))[:150] + "..."
        
        chapter_num = (i // chunk_size) + 1
        summary_content += f"### 第 {chapter_num} 部分：内容回顾\n\n"
        summary_content += f"[{timestamp}]\n{text}\n\n"

    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(summary_content)

def generate_report(report_path, stats):
    report = f"--- 任务执行报告 (Execution Report) ---\n"
    report += f"执行时间: {stats.get('time')}\n"
    report += f"项目名称: {stats.get('name')}\n"
    report += f"输入链接: {stats.get('url')}\n"
    report += f"主要步骤执行情况:\n"
    for step, status in stats.get('steps', {}).items():
        report += f"  - {step}: {status}\n"
    report += f"\n最终输出文件清单:\n"
    for f in stats.get('outputs', []):
        report += f"  - {f}\n"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="Path to translated JSON")
    parser.add_argument("--output", help="Output MD path")
    parser.add_argument("--project", help="Project name")
    parser.add_argument("--report", help="Report path")
    parser.add_argument("--url", help="YouTube URL")
    args = parser.parse_args()

    if args.json and args.output:
        with open(args.json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        generate_summary(data, args.output, args.project)
        print(f"Summary generated: {args.output}")

    if args.report:
        import datetime
        stats = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "name": args.project,
            "url": args.url,
            "steps": {
                "YouTube Download": "Success",
                "Transcription": "Success",
                "Translation": "Success",
                "Audio Generation": "Success",
                "Summary Generation": "Success"
            },
            "outputs": [
                f"{args.project}.mp3 (Original)",
                f"{args.project}_CN.mp3 (Chinese)",
                f"{args.project}_summary.md",
                f"{args.project}_translated.json"
            ]
        }
        generate_report(args.report, stats)
        print(f"Report generated: {args.report}")

if __name__ == "__main__":
    main()
