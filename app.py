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
@trace("Route: Integrated Video & Site Analysis")
def analyze_video():
    data = request.get_json()
    video_url = data.get('url')
    if not video_url:
        return jsonify({"status": "error", "message": "URL 필요"}), 400
        
    video_id = get_video_id(video_url)

    # 1. DB 캐시 확인
    cached = db_handler.get_analysis_result(video_id)
    if cached and "script_analysis" in cached and "trust_report" in cached:
        print(f"📦 [Cache Hit] 기존 데이터 반환: {video_id}")
        # 캐시된 데이터를 보낼 때도 한글 보존을 위해 직접 응답 생성
        final_res = {
            "status": "success",
            "data": {
                "video_id": video_id,
                "analysis_result": cached["script_analysis"],
                "site_info": cached["trust_report"],
                "cached": True
            }
        }
        return Response(json.dumps(final_res, ensure_ascii=False), mimetype='application/json')

    try:
        # 2. 통합 분석 실행
        hint_data = cached if cached and cached.get('title') else None
        integrated_report = tracer.analyze(video_url, hint_data=hint_data)

        # 3. 데이터 매핑
        script_analysis_data = {
            "brand": integrated_report.get("brand"),
            "corporate_name": integrated_report.get("Corporate Name"),
            "product_name": integrated_report.get("product_name"),
            "evidence": integrated_report.get("evidence"),
            "landing_page_url": integrated_report.get("fined_landing_page")
        }

        trust_report_data = {
            "step1_video_discovery": {
                "brand": integrated_report.get("brand"),
                "product_name": integrated_report.get("product_name"),
                "landing_page_url": integrated_report.get("fined_landing_page")
            },
            "step2_deep_verification": {
                "analysis_case": integrated_report.get("analysis_case"),
                "trust_analysis": integrated_report.get("trust_analysis"),
                "review": integrated_report.get("review")
            }
        }

        # 4. DB 저장
        save_payload = {
            "video_id": video_id,
            "script_analysis": script_analysis_data,
            "trust_report": trust_report_data,
            "client_ip": request.remote_addr,
            "user_agent": request.headers.get('User-Agent', '')
        }
        if cached:
            cached.update(save_payload)
            db_handler.save_analysis_result(cached)
        else:
            db_handler.save_analysis_result(save_payload)

        # 5. [핵심] 최종 응답 생성 (한글 깨짐 방지)
        final_result = {
            "status": "success",
            "data": {
                "video_id": video_id,
                "analysis_result": script_analysis_data,
                "site_info": trust_report_data,
            }
        }
        
        # ensure_ascii=False로 설정하여 한글을 유니코드 이스케이프 없이 그대로 직렬화
        json_string = json.dumps(final_result, ensure_ascii=False)
        
        # Flask Response를 생성하며 데이터와 타입, 인코딩을 명시함
        return Response(
            response=json_string,
            status=200,
            mimetype='application/json',
            content_type='application/json; charset=utf-8'
        )

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

############## 건드리지 말 것 ##############

if __name__ == '__main__':
    # 참고: MCP 커넥터는 첫 요청 시 Lazy 초기화됩니다 (이벤트 루프 충돌 방지)
    port = int(os.environ.get("PORT", 5173))
    app.run(debug=True, host='0.0.0.0', port=port)

########################################