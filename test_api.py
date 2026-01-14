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
    try:
        res = requests.get(f"{base_url}/")
        print(f"Status: {res.status_code}, Response: {res.text[:100]}")
    except Exception as e:
        print(f"Error: {e}")

    # 2. Health
    print("\n[GET /health]")
    try:
        res = requests.get(f"{base_url}/health")
        print(f"Status: {res.status_code}, Response: {res.text[:100]}")
    except Exception as e:
        print(f"Error: {e}")

    # 3. Transcript
    print("\n[POST /transcript]")
    payload = {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    try:
        res = requests.post(f"{base_url}/transcript", json=payload)
        print(f"Status: {res.status_code}, Response: {res.text[:100]}")
    except Exception as e:
        print(f"Error: {e}")

    # 4. Analyze (Gemini)
    print("\n[POST /analyze]")
    payload = {"script": "테스트 스크립트입니다."}
    try:
        res = requests.post(f"{base_url}/analyze", json=payload)
        print(f"Status: {res.status_code}, Response: {res.text[:100]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # app.py의 중간(185라인)에서 서버가 시작되면 5000번 포트가 사용됩니다.
    # 만약 185라인을 주석 처리하고 실행하신다면 8080번 포트가 사용됩니다.
    import sys
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    
    test_api(port)
