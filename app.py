from models.dynamodb import db_handler
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from utils.profiler import trace, profiler
#from site_analyzer import LinkTracer
import os
import json
from yt_shorts import get_video_id, get_youtube_comments
import asyncio
from youtube_transcript_api import YouTubeTranscriptApi

app = Flask(__name__)
CORS(app) # 모든 origin에 대해 CORS 허용
app.config['JSON_AS_ASCII'] = False
app.json.ensure_ascii = False # Flask 2.2+ 에서 한글 깨짐 방지

@app.after_request
def after_each_request(response):
    profiler.print_summary()
    return response

@app.route('/')
@trace("Route: Home")
def home():
    return jsonify({
        "status": "success",
        "message": "Hello, World! Flask server is running."
    })

# ==========================================
# 2. [순호] 기본 영상 정보 조회 (Fast)
# ==========================================
@app.route('/api/video/info', methods=['POST'])
@trace("Route: Get video info")
def get_video_info():
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    if not url: return jsonify({"status": "error", "message": "URL 필요"}), 400

    try:
        # 1. 변수 정의 (NameError 해결 포인트)
        api_key = os.getenv("Youtube_API_Key") # 변수명을 명확히 할당
        v_id = get_video_id(url)
        
        # [NEW] DB에서 기존 정보 확인
        from models.dynamodb import db_handler
        cached_info = db_handler.get_analysis_result(v_id)
        if cached_info and cached_info.get("title"):
             print(f"✅ [Cache Hit] Returning cached info for {v_id}")
             return jsonify({
                "status": "success",
                "data": {
                    "video_id": v_id, 
                    "title": cached_info.get("title"),
                    "channel_name": cached_info.get("channel_name"), 
                    "published_at": cached_info.get("published_at"), 
                    "thumbnail_url": cached_info.get("thumbnail_url"), 
                    "cached": True
                }
            })

        # 2. 영상 다운로드(yt-dlp) 없이 메타데이터만 호출 (속도 개선)
        from yt_shorts import get_metadata_only # 새로 만든 함수 임포트
        item = get_metadata_only(api_key, v_id)
        
        if not item:
            return jsonify({"status": "error", "message": "영상을 찾을 수 없습니다."}), 404

        snippet = item.get('snippet', {})
        stats = item.get('statistics', {})

        # 3. 이상적인 명세서(Ideal Spec) 규격에 맞춘 응답 구성 
        response_data = {
            "video_id": v_id, 
            "title": snippet.get("title"),
            "channel_name": snippet.get("channelTitle"), 
            "published_at": snippet.get("publishedAt"), 
            "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url")
            }

        # [NEW] DB 저장 (Partial Update)
        try:
            client_ip = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')
            response_data["client_ip"] = client_ip
            response_data["user_agent"] = user_agent
            db_handler.save_analysis_result(response_data)
        except Exception as e:
            print(f"⚠️ [DB Error] {e}")

        return jsonify({
            "status": "success",
            "data": response_data
        })
    except Exception as e:
        # 에러 메시지를 구체적으로 확인하기 위해 e 출력
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/video/check-transcript', methods=['POST'])
@trace("Route: Check Transcript Exists")
def check_transcript():
    """
    유튜브 URL을 입력받아 자막 존재 여부만 빠르게 검증
    API 명세: POST /api/video/check-transcript
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({
            "status": "error",
            "message": "Missing 'url' in request body"
        }), 400

    video_url = data.get('url')
    
    # URL에서 비디오 아이디 추출 
    video_id = get_video_id(video_url)
    if not video_id:
        return jsonify({
            "status": "success", 
            "data": {"is_valid": False, "reason": "유효하지 않은 유튜브 URL형식"}
        }), 200

    try:
        # v1.0+: 인스턴스 메서드로 자막 메타데이터 목록 빠르게 조회
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)
        
        return jsonify({
            "status": "success",
            "data": {
                "is_valid": True,          
                "has_transcript": True
            }
        }), 200

    except Exception as e:
        error_name = type(e).__name__
        # 자막이 비활성화 되어 있거나 찾는 언어 자막이 없는 경우 (검증 실패)
        if error_name in ('TranscriptsDisabled', 'NoTranscriptFound', 'NoTranscriptAvailable'):
            return jsonify({
                "status": "success",
                "data": {
                    "is_valid": False,
                    "has_transcript": False,
                    "reason": "해당 영상에 자막이 제공되지 않습니다."
                }
            }), 200
        
        return jsonify({
            "status": "error",
            "message": f"자막 확인 중 오류 발생: {str(e)}"
        }), 500

app.config['JSON_AS_ASCII'] = False
app.json.ensure_ascii = False

# [중요] 전역 인스턴스 생성
#tracer = LinkTracer()

@app.route('/api/video/analyze', methods=['POST'])
@trace("Route: Integrated Analysis")
def analyze_video():
    data = request.get_json()
    video_url = data.get('url')
    device_id = data.get('device_id')
    
    if not video_url:
        return jsonify({"status": "error", "message": "URL 필요"}), 400
        
    video_id = get_video_id_safely(video_url)

    # 1. DB 캐시 확인
    cached = db_handler.get_analysis_result(video_id)
    if cached and "analysis_result" in cached:
        return Response(json.dumps({"status": "success", "data": cached}, ensure_ascii=False), mimetype='application/json')

    # 2. [개선] 데이터 먼저 긁기 (LinkTracer가 중복 호출하지 않게 함)
    # 유튜브 API 정보(제목, 채널명 등)를 한 번에 가져와서 넘겨줍니다.
    # tracer.analyze 내부에서 다시 API를 호출하지 않도록 hint_data를 구성합니다.
    
    try:
        # 비동기 병렬 분석 실행
        # analyze_ad 내부에서 LinkTracer, FactCheck, PatentCheck가 동시에 돌아갑니다.
        from gemini_main import analyze_ad
        
        # hint_data를 통해 LinkTracer에 필요한 정보를 미리 전달
        report_json, script_text = asyncio.run(analyze_ad(
            video_url=video_url,
            device_id=device_id
        ))

        analysis_result = json.loads(report_json)

        save_payload = {
        "video_id": video_id,
        "analysis_result": analysis_result,
        "trust_report": {},
        "script_text": script_text, # 이제 여기서 추출된 자막이 들어갑니다!
        "device_id": device_id
        }
        db_handler.save_analysis_result(save_payload)

        # 3. 최종 응답 생성 및 DB 저장 (기존 로직 유지)
        return Response(
            response=json.dumps({"status": "success", "data": analysis_result}, ensure_ascii=False),
            status=200,
            mimetype='application/json',
            content_type='application/json; charset=utf-8'
        )
    
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500
    
import re

def get_video_id_safely(url):
    """
    LinkTracer 없이도 유튜브 URL에서 비디오 ID를 추출하는 독립 함수
    """
    if not url:
        return None
        
    patterns = [r'shorts/([\w-]+)', r'v=([\w-]+)', r'be/([\w-]+)']
    for pattern in patterns:
        match = re.search(pattern, url)
        if match: 
            return match.group(1)
            
    # 패턴 매칭 실패 시 마지막 슬래시 뒤를 가져오는 예외 처리
    return url.split('/')[-1].split('?')[0]
    
def get_youtube_transcript2(video_url, languages=['ko', 'en']):
    print(f"[DEBUG] get_youtube_transcript2 called with URL: {video_url}")
    from yt_shorts import get_video_id
    video_id = get_video_id(video_url) # 다양한 URL 지원
    print(f"[DEBUG] Extracted Video ID: {video_id}")

    if not video_id: 
        print("[DEBUG] Failed to extract Video ID.")
        return None

    try:
        # [DEBUG] 자막 불러오기 시도
        print(f"[DEBUG] Attempting to fetch transcript for {video_id} with languages={languages}")
        
        # v1.0+: 인스턴스 메서드로 자막 직접 조회
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=languages)
        print("[DEBUG] Success fetching transcript.")

        # 순수 텍스트로 변환하여 Gemini 분석에 최적화 (TextFormatter 대체)
        print("[DEBUG] Formatting transcript...")
        formatted_text = "\n".join([snippet.text for snippet in transcript]).strip()
        print(f"[DEBUG] Formatted text length: {len(formatted_text)}")
        return formatted_text

    except Exception as e:
        print(f"❌ [ERROR] get_youtube_transcript2 failed: {e}")
        import traceback
        print(traceback.format_exc())
        return None
    
############## 건드리지 말 것 ##############

if __name__ == '__main__':
    # 참고: MCP 커넥터는 첫 요청 시 Lazy 초기화됩니다 (이벤트 루프 충돌 방지)
    port = int(os.environ.get("PORT", 5173))
    app.run(debug=True, host='0.0.0.0', port=port)

########################################