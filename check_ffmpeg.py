
import subprocess
import shutil

def check():
    print(f"shutil.which('ffmpeg'): {shutil.which('ffmpeg')}")
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("FFmpeg execution: SUCCESS")
    except Exception as e:
        print(f"FFmpeg execution: FAILED ({e})")

if __name__ == "__main__":
    check()
