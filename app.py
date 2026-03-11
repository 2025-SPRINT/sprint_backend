from models.dynamodb import db_handler
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from utils.profiler import trace, profiler
from site_analyzer import LinkTracer
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
tracer = LinkTracer()

@app.route('/api/video/analyze', methods=['POST'])
@trace("Route: Integrated Video & Site Analysis (AD-ASTRA Final)")
def analyze_video():
    data = request.get_json()
    video_url = data.get('url')
    device_id = data.get('device_id')
    
    if not video_url:
        return jsonify({"status": "error", "message": "URL 필요"}), 400
        
    video_id = tracer.extract_video_id(video_url)

    # 1. DB 캐시 확인
    cached = db_handler.get_analysis_result(video_id)
    if cached and "analysis_result" in cached:
        return Response(json.dumps({"status": "success", "data": cached}, ensure_ascii=False), mimetype='application/json')

    # 2. 통합 분석 실행 함수 (LinkTracer + Gemini Analyze AD)
    async def run_analysis():
        # (1) LinkTracer를 통해 브랜드/사이트/자막/댓글 수집 및 1차 분석
        # 이 과정에서 tracer.analyze 내부의 수집 로직을 활용합니다.
        # hint_data가 없으면 tracer가 알아서 API를 호출합니다.
        trust_report = await asyncio.to_thread(tracer.analyze, video_url)
        
        # (2) 필요한 텍스트 데이터 추출 (LinkTracer가 수집한 데이터 활용)
        # 만약 tracer.analyze 결과에 script나 comments가 포함되도록 tracer 클래스를 수정했다면 그것을 쓰고,
        # 아니면 여기서 다시 수집합니다.
        script_text = await asyncio.to_thread(tracer.get_transcript, video_id)
        comments_text = await asyncio.to_thread(tracer.get_comments, video_id)

        # (3) [핵심] Gemini 2차 심화 분석 실행
        from gemini_main import analyze_ad
        report = await analyze_ad(
        script_text=script_text,
        site_details=trust_report.get('trust_analysis', '정보 없음'), 
        comments_data=comments_text,
        # 딕셔너리 객체를 그대로 넘겨주거나, 필요한 키를 가진 새 딕셔너리를 만듭니다.
        discovery_data={
            "brand": trust_report.get('brand', '미확인'),
            "evidence": trust_report.get('evidence', '근거 없음')
            }, 
        )

        return script_text, trust_report, report, comments_text

    try:
        # 비동기 실행 및 데이터 언패킹 (민석 님이 요청하신 4개 변수 구조)
        script_text, trust_report, report, comments_data = asyncio.run(run_analysis())

        # JSON 파싱 안전 처리
        try:
            analysis_result = json.loads(report) if isinstance(report, str) else report
        except (json.JSONDecodeError, TypeError):
            analysis_result = report

        # 3. DB 저장 페이로드
        save_payload = {
            "video_id": video_id,
            "script_analysis": analysis_result, # 최종 Gemini 리포트
            "trust_report": trust_report,        # LinkTracer가 찾은 사이트/브랜드 정보
            "script_text": script_text,
            "device_id": device_id
        }
        
        db_handler.save_analysis_result(save_payload)

        # 4. 최종 응답
        final_result = {
            "status": "success",
            "data": {
                "video_id": video_id,
                "analysis_result": analysis_result,
                "site_info": trust_report,
            }
        }
        
        return Response(
            response=json.dumps(final_result, ensure_ascii=False),
            status=200,
            mimetype='application/json',
            content_type='application/json; charset=utf-8'
        )
    
    except Exception as e:  # 이 블록이 누락되었는지 확인하세요!
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500
    
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