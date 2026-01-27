import subprocess
import json
import time

urls = [
    "https://www.youtube.com/shorts/ZVEPzfK8QK0",
    "https://www.youtube.com/shorts/nTsOh2w_JHE",
    "https://www.youtube.com/shorts/bA0ZQe-FTx4"
]

base_url = "http://localhost:5173"

endpoints = [
    "/api/video/info",
    "/api/video/analyze" 
    # Skip detect to finish fast
]

def run_curl(url, endpoint):
    full_url = f"{base_url}{endpoint}"
    data = json.dumps({"url": url})
    cmd = [
        "curl", "-X", "POST", full_url,
        "-H", "Content-Type: application/json",
        "-d", data,
        "-s"
    ]
    
    print(f"Calling {full_url} for {url}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(f"Status: {result.returncode}")
        return result.stdout
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    print("Starting Maining 3 Tests...")
    for url in urls:
        print(f"\n--- Testing URL: {url} ---")
        for ep in endpoints:
            run_curl(url, ep)
            time.sleep(2)
    print("\nDone.")
