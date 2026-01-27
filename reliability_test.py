import subprocess
import json
import time

urls = [
    "https://www.youtube.com/shorts/45pMKwnapmA",
    "https://www.youtube.com/watch?v=iSo3l6j5KmA",
    "https://www.youtube.com/watch?v=nj8tGTQ1NgM",
    "https://www.youtube.com/watch?v=_5s0EDFhGyc",
    "https://www.youtube.com/watch?v=LJZWQv3-rvA",
    "https://www.youtube.com/shorts/u9R-i9tXvbM",
    "https://www.youtube.com/shorts/nrGYlDcC3tk",
    "https://www.youtube.com/shorts/ZVEPzfK8QK0",
    "https://www.youtube.com/shorts/nTsOh2w_JHE",
    "https://www.youtube.com/shorts/bA0ZQe-FTx4"
]

base_url = "http://localhost:5173"

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
        "-s" # Silent mode
    ]
    
    print(f"Calling {full_url} for {url}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120) # 2 min timeout
        print(f"Status: {result.returncode}")
        # print(f"Response: {result.stdout[:100]}...") # Print first 100 chars
        return result.stdout
    except subprocess.TimeoutExpired:
        print("Timeout detected!")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    print("Starting Reliability Test...")
    # Wait a bit for server to be fully ready
    time.sleep(5)
    
    results = {}
    
    for url in urls:
        print(f"\n--- Testing URL: {url} ---")
        results[url] = {}
        for ep in endpoints:
            response = run_curl(url, ep)
            results[url][ep] = response
            # Add a small delay between requests to avoid overwhelming
            time.sleep(2)
            
    print("\nTest Complete.")
