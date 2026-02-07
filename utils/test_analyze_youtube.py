import requests
import json
import sys

def test_analyze_youtube(video_url, port=8080):
    """
    /analyze-youtube API 엔드포인트를 테스트하는 스크립트입니다.
    """
    url = f"http://localhost:{port}/transcript"
    
    # 테스트에 사용할 페이로드
    # 인코딩을 위해 한글 데이터 포함 가능
    payload = {
        "video_url": video_url,
        "languages": ["ko", "en"]
    }
    
    print(f"\n🚀 API 요청 중: {url}")
    print(f"📦 페이로드: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        # requests.post의 json 매개변수를 사용하면 자동으로 UTF-8 인코딩 및 Content-Type: application/json 설정이 이루어집니다.
        response = requests.post(url, json=payload, timeout=300) # 분석에 시간이 걸릴 수 있으므로 타임아웃 넉넉히 설정
        
        print(f"\n✅ 응답 코드: {response.status_code}")
        
        try:
            # 응답 본문을 JSON으로 파싱
            result = response.json()
            # 한글이 깨지지 않도록 ensure_ascii=False 설정하여 출력
            print("📝 분석 리포트 결과:")
            print("-" * 50)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("-" * 50)
            
            if response.status_code == 200:
                print("\n✨ 테스트 성공!")
            else:
                print(f"\n❌ 테스트 실패 (상태 코드: {response.status_code})")
                
        except json.JSONDecodeError:
            print(f"❌ JSON 파싱 실패. 응답 내용: {response.text[:1000]}")
            
    except requests.exceptions.ConnectionError:
        print(f"❌ 서버 연결 실패. {url} 이 실행 중인지 확인하세요.")
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")

if __name__ == "__main__":
    # 기본 테스트용 쇼츠 URL (키 성장 관련 광고 등)
    default_url = "https://www.youtube.com/watch?v=QYbtbUm8OMA"
    
    # 명령줄 인자로 URL을 받을 수 있도록 함
    target_url = sys.argv[1] if len(sys.argv) > 1 else default_url
    target_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    
    test_analyze_youtube(target_url, target_port)
