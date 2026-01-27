import subprocess
import json
import time

# The last 4 urls (including the one that timed out locally + the 3 remaining)
urls = [
    "https://www.youtube.com/shorts/nrGYlDcC3tk", # Timed out locally
    "https://www.youtube.com/shorts/ZVEPzfK8QK0",
    "https://www.youtube.com/shorts/nTsOh2w_JHE",
    "https://www.youtube.com/shorts/bA0ZQe-FTx4"
]

base_url = "https://uncloistral-pseudoheroical-milena.ngrok-free.dev"

endpoints = [
    "/api/video/info",
    "/api/video/analyze",
    "/api/video/detect"
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
        # Remote server might take time for detect, giving 5 mins timeout
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print(f"Status: {result.returncode}")
        if result.returncode == 0:
             print(f"Response (truncated): {result.stdout[:200]}...")
        else:
             print(f"Error Output: {result.stderr}")
        return result.stdout
    except subprocess.TimeoutExpired:
        print("Timeout detected!")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    print(f"Starting Remote Reliability Test against {base_url}...")
    
    for url in urls:
        print(f"\n--- Testing URL: {url} ---")
        for ep in endpoints:
            run_curl(url, ep)
            # Small delay to be nice to the server
            time.sleep(2)
            
    print("\nRemote Test Complete.")
