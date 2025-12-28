import requests
import time
import os

URL = "http://localhost:8000/generate"

def test_provider(provider, text, speaker="Ben"):
    print(f"Testing {provider} with speaker {speaker}...")
    start = time.time()
    try:
        payload = {
            "text": text,
            "speaker": speaker,
            "provider": provider
        }
        response = requests.post(URL, json=payload, timeout=60)
        duration = time.time() - start
        
        if response.status_code == 200:
            filename = f"test_{provider}.{'mp3' if provider == 'minimax' else 'pcm'}"
            with open(filename, 'wb') as f:
                f.write(response.content)
            size = os.path.getsize(filename)
            print(f"✅ Success! ({duration:.2f}s) - Saved {filename} ({size} bytes)")
        else:
            print(f"❌ Failed! ({duration:.2f}s) - Status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    # Wait for server to potentially start
    time.sleep(2)
    
    # Test Gemini
    test_provider("gemini", "This is a test of the Gemini generation.")
    
    # Test Minimax
    test_provider("minimax", "这是一个Minimax模型的中文测试。", speaker="Ben")
