import requests
import json

# 현재 app.py 상에서 185번 라인의 app.run()이 먼저 실행되므로
# 기본 포트인 5000번과, 마지막에 의도하신 8080번을 모두 테스트할 수 있도록 작성했습니다.
# macOS 사용 시 5000번 포트는 'AirPlay 수신 모드'와 충돌하여 403 에러가 발생할 수 있습니다.

def test_api(port):
    base_url = f"http://localhost:{port}"
    print(f"\n=== Testing API at {base_url} ===")
    
    # 1. Home
    print("\n[GET /]")
    make_request(f"{base_url}/", "GET")

    # 2. Health
    print("\n[GET /health]")
    make_request(f"{base_url}/health", "GET")

    # 3. Transcript
    print("\n[POST /transcript]")
    payload = {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    make_request(f"{base_url}/transcript", "POST", payload)

    # 4. Analyze (Gemini)
    print("\n[POST /analyze]")
    payload = {"script": "이 제품은 특허 제10-2023-1234567호로 보호받고 있습니다."}
    make_request(f"{base_url}/analyze", "POST", payload)

def make_request(url, method, payload=None):
    try:
        if method == "GET":
            res = requests.get(url)
        else:
            res = requests.post(url, json=payload)
        
        try:
            json_data = res.json()
            print(f"Status: {res.status_code}")
            print(f"Response: {json.dumps(json_data, ensure_ascii=False, indent=2)}")
        except:
            print(f"Status: {res.status_code}, Response: {res.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import sys
    # Defaults to 8080 as per the user's latest app.py structure
    port = 8080
    if len(sys.argv) > 1:
        port = sys.argv[1]
    
    test_api(port)
