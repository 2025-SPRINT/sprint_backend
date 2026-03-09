from models.dynamodb import db_handler
from flask import Flask, jsonify, request
from flask_cors import CORS
from utils.profiler import trace, profiler
from site_analyzer import LinkTracer, BrandTrustAnalyzer
import os
import json
from yt_shorts import get_video_id, get_youtube_comments
import asyncio
from youtube_transcript_api import YouTubeTranscriptApi
from gemini_main import main as gemini_analyze, PROMPT

app = Flask(__name__)
CORS(app) # 모든 origin에 대해 CORS 허용
app.config['JSON_AS_ASCII'] = False

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

def get_safe_metadata(result):
    """result가 경로(str)면 파일을 읽고, 사전(dict)이면 그대로 반환"""
    if isinstance(result, str):
        json_path = os.path.join(result, "data_api_origin.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f), result
        return {}, result
    return result, result.get("storage_path")

# youtube_transcript_api v1.0+: 예외 클래스는 except 블록에서 타입명으로 처리

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

@app.route('/api/video/analyze', methods=['POST'])
@trace("Route: Integrated Video & Site Analysis (Fail-safe)")
def analyze_video():
    data = request.get_json()
    video_url = data.get('url')
    video_id = get_video_id(video_url)

    async def run_analysis():
        # 1. 자막 가져오기
        task_transcript = asyncio.to_thread(get_youtube_transcript2, video_url)
        
        # 2. 사이트 추적 (tracer 인스턴스는 여기서만 사용)
        task_site_trace = asyncio.to_thread(run_site_verification, video_url)
        
        # 3. [수정] yt_shorts.py에 정의된 독립 함수를 직접 호출 (가장 안전)
        from yt_shorts import get_youtube_comments
        task_comments = asyncio.to_thread(get_youtube_comments, video_url) # video_url 전달

        script_text, trust_report, comments_raw = await asyncio.gather(
            task_transcript, task_site_trace, task_comments
        )

        # 댓글 데이터(리스트)를 Gemini가 읽기 좋게 문자열로 변환
        if isinstance(comments_raw, list):
            comments_text = " | ".join([c['text'] for c in comments_raw])
        else:
            comments_text = str(comments_raw)

        # 4. Gemini 분석 호출
        from gemini_main import evaluate_with_site_info
        report = await evaluate_with_site_info(
                                                script_text, 
                                                trust_report.get('step2_deep_verification'), # 웹사이트 상세 분석 결과
                                                comments_text,                                # 댓글 데이터
                                                trust_report.get('step1_video_discovery')    # 브랜드/법인/상품명 추출 결과 (이게 누락됨!)
                                            )
        
        return (script_text, trust_report, report, comments_text), None

    try:
        result, error = asyncio.run(run_analysis())
        script_text, trust_report, report, comments_data = result

        try:
            # Gemini 응답이 문자열일 경우 JSON 파싱
            analysis_result = json.loads(report) if isinstance(report, str) else report
        except:
            analysis_result = report

        # DB 저장 시도
        try:
            client_ip = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')
            db_handler.save_analysis_result({
                "video_id": video_id,
                "script_analysis": analysis_result,
                "trust_report": trust_report,
                "client_ip": client_ip,
                "user_agent": user_agent
            })
        except: pass

        return jsonify({
            "status": "success",
            "data": {
                "video_id": video_id,
                "analysis_result": analysis_result,
                "site_info": trust_report
            }
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

# 사이트 분석 로직을 별도 함수로 분리 (병렬 처리를 위해)
def run_site_verification(video_url):
    from site_analyzer import LinkTracer, BrandTrustAnalyzer
    tracer = LinkTracer()
    
    # Step 1: 여기서 브랜드명, 법인명, 상품명이 추출됩니다.
    step1_res = tracer.analyze(video_url)
    final_link = step1_res.get('landing_page_url')
    
    step2_res = None
    if final_link and "http" in final_link:
        analyzer = BrandTrustAnalyzer(tracer.client)
        # Step 2: 상세 신뢰도 리포트 생성
        step2_res = analyzer.generate_trust_report(
            target_url=final_link,
            product_name=step1_res.get('product_name'),
            brand=step1_res.get('brand')
        )
        
    return {
        "step1_video_discovery": step1_res, # 여기에 브랜드/법인/상품명 포함됨
        "step2_deep_verification": step2_res
    }
    
# TextFormatter는 v1.0+에서 제거됨 — 수동 텍스트 변환 사용
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
    
# ==============사이트 분석 로직====================
@app.route('/api/video/trace-trust', methods=['POST'])
@trace("Route: Trace Link and Brand Trust")
def trace_link_and_trust():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"status": "error", "message": "URL 필요"}), 400

    v_id = get_video_id(url)

    # 1. DB 캐시 확인 (중복 분석 방지 및 메타데이터 획득)
    cached = db_handler.get_analysis_result(v_id)
    
    # 만약 신뢰도 리포트까지 이미 있다면 즉시 반환
    if cached and "trust_report" in cached:
        return jsonify({"status": "success", "data": cached["trust_report"], "cached": True})

    try:
        tracer = LinkTracer() 
        
        # Step 1: 영상 분석 및 구매 링크 추적
        # [수정] DB에 저장된 기본 정보(cached)를 analyze 함수에 전달합니다.
        step1_res = tracer.analyze(url, hint_data=cached) 
        final_link = step1_res.get('landing_page_url')

        # Step 2: 구매 사이트 신뢰도 실사
        step2_res = "유효 링크 없음"
        if final_link and "http" in final_link:
            analyzer = BrandTrustAnalyzer(tracer.client)
            step2_res = analyzer.generate_trust_report(
                target_url=final_link,
                product_name=step1_res.get('product_name'),
                brand=step1_res.get('brand')
            )

        final_report = {
            "step1_video_discovery": step1_res,
            "step2_deep_verification": step2_res
        }

        # 3. 결과 DB 저장
        # [수정] 분석된 리포트뿐만 아니라, 분석 과정에서 사용된 메타데이터도 함께 업데이트/보존합니다.
        try:
            client_ip = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')
            db_handler.save_analysis_result({
                "video_id": v_id,
                "trust_report": final_report,
                "client_ip": client_ip,
                "user_agent": user_agent
            })
        except: pass

        return jsonify({"status": "success", "data": final_report})

    except Exception as e:
        print(f"❌ [Error] {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

############## 건드리지 말 것 ##############

if __name__ == '__main__':
    # 참고: MCP 커넥터는 첫 요청 시 Lazy 초기화됩니다 (이벤트 루프 충돌 방지)
    port = int(os.environ.get("PORT", 5173))
    app.run(debug=True, host='0.0.0.0', port=port)

########################################