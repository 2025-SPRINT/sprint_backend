from flask import Flask, jsonify
from flask_cors import CORS
from utils.profiler import trace, profiler

# To-DO

# 1. 간단한 DB 구축: DB에 영상 info, AI 생성률 분석, 분석 리포트 저장
# 2. 분석 완료한 영상은 DB에 저장 후 다운로드한 영상 파일 삭제 로직 구현

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
# ========================================
from flask import Flask, jsonify, request
from site_analyzer import LinkTracer, BrandTrustAnalyzer
import os
import json
# import cv2
# import imageio
from yt_shorts import get_video_id, collect_and_split_data, get_or_save_api_key
# from models.npr_model.npr_wrapper import NPRDetector

# ==========================================
# 1. 전역 설정 및 모델 로드
# ==========================================
# npr_detector = NPRDetector(model_filename="model_epoch_last_3090.pth")

def get_safe_metadata(result):
    """result가 경로(str)면 파일을 읽고, 사전(dict)이면 그대로 반환"""
    if isinstance(result, str):
        json_path = os.path.join(result, "data_api_origin.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f), result
        return {}, result
    return result, result.get("storage_path")



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
        api_key = get_or_save_api_key() # 변수명을 명확히 할당
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
                    "view_count": cached_info.get("view_count"),
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
            "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"), 
            "view_count": stats.get("viewCount") 
        }

        # [NEW] DB 저장 (Partial Update)
        try:
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

# ==========================================
# 3. 딥페이크 탐지 (NPR 원본 로직 적용 + 기존 응답 구조 유지)
# ==========================================

# @app.route('/api/video/detect', methods=['POST'])
# @trace("Route: Analyze NPR (Deepfake)")
# def detect_deepfake():
#     """
#     NPR-CVPR2024 원본 추론 로직을 사용하여 
#     Real 및 Fake 프레임의 평균 점수를 계산합니다.
#     """
#     data = request.get_json(silent=True) or {}
#     url = data.get("url")
#     interval = int(data.get("interval", 20))
#     threshold = float(data.get("threshold", 0.5))

#     if not url:
#         return jsonify({"status": "error", "message": "URL이 필요합니다."}), 400

#     try:
#         print(f"\n🚀 영상 분석 시작 (점수 평균 계산 모드)") 
        
#         v_id = get_video_id(url)
#         res = collect_and_split_data(get_or_save_api_key(), url, v_id)
#         _, storage_path = get_safe_metadata(res)
        
#         video_path = os.path.join(storage_path, "video.mp4")
#         if not os.path.exists(video_path):
#             for f in os.listdir(storage_path):
#                 if f.endswith((".mp4", ".webm")):
#                     video_path = os.path.join(storage_path, f)
#                     break
        
#         cap = cv2.VideoCapture(video_path)
        
#         # 점수 계산을 위한 변수 초기화
#         fake_scores = []
#         real_scores = []
#         analyzed_frames = 0
#         frame_idx = 0

#         try:
#             if not cap.isOpened():
#                 raise RuntimeError(f"비디오를 열 수 없음: {video_path}")

#             while True:
#                 ret, frame = cap.read()
#                 if not ret:
#                     break

#                 if frame is None or frame.size == 0:
#                     frame_idx += 1
#                     continue

#                 # Interval마다 분석 수행
#                 if frame_idx % interval == 0:
#                     try:
#                         # npr_detector로부터 0~1 사이의 score 획득
#                         score = float(npr_detector.predict_image(frame))
                        
#                         # threshold 기준으로 Real/Fake 분리하여 리스트에 저장
#                         if score > threshold:
#                             fake_scores.append(score)
#                         else:
#                             real_scores.append(score)
                            
#                         analyzed_frames += 1
#                     except Exception as e:
#                         print(f"[WARN] {frame_idx}번 프레임 분석 중 모델 에러: {e}")
#                 frame_idx += 1

#         finally:
#             cap.release()

#         if analyzed_frames == 0:
#             raise RuntimeError("분석된 프레임이 없습니다.")

#         # [평균 점수 계산]
#         # 리스트가 비어있을 경우(0)를 대비해 처리
#         avg_fake_score = sum(fake_scores) / len(fake_scores) if fake_scores else 0.0
#         avg_real_score = sum(real_scores) / len(real_scores) if real_scores else 0.0

#         print(f"✅ 분석 완료: Fake 평균 {round(avg_fake_score, 4)}, Real 평균 {round(avg_real_score, 4)}")

#         return jsonify({
#             "status": "success",
#             "data": {
#                 "video_id": v_id,
#                 "detection_result": {
#                     "avg_fake_score": round(avg_fake_score, 4),  # Fake로 판정된 프레임들의 평균 점수
#                     "avg_real_score": round(avg_real_score, 4),  # Real로 판정된 프레임들의 평균 점수
#                     "fake_frame_count": len(fake_scores),
#                     "real_frame_count": len(real_scores),
#                     "total_analyzed_frames": analyzed_frames
#                 }
#             }
#         })

#     except Exception as e:
#         import traceback
#         print(traceback.format_exc())
#         return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 3. 딥페이크 탐지 (Gemini 2.5 Flash 적용)
# ==========================================
import shutil
import gemini_graph.video as video
from models.dynamodb import db_handler

# DB 테이블 초기 세팅 (앱 시작 시 1회 실행)
try:
    db_handler.create_table_if_not_exists()
except:
    pass

@app.route('/api/video/detect', methods=['POST'])
@trace("Route: Analyze Video with Gemini 2.5 Flash (Deepfake)")
def detect_deepfake_with_gemini_25():
    """
    Gemini 2.5 Flash를 사용하여 영상의 AI/Real 확률을 분석합니다.
    """
    data = request.get_json()
    url = data.get("url")
    if not url: return jsonify({"status": "error", "message": "URL 필요"}), 400
    
    try:
        v_id = get_video_id(url)
        
        # [NEW] DB에서 기존 분석 결과 확인
        cached_result = db_handler.get_analysis_result(v_id)
        if cached_result:
            print(f"✅ [Cache Hit] Returning cached result for {v_id}")
            return jsonify({
                "status": "success",
                "data": {
                    "video_id": v_id,
                    "detection_result": {
                        "avg_fake_score": round(cached_result.get('ai_score', 0), 4),
                        "avg_real_score": round(cached_result.get('human_score', 0), 4),
                        "fake_frame_count": 1,
                        "real_frame_count": 1,
                        "total_analyzed_frames": 1,
                        "cached": True # 캐시된 데이터임을 표시
                    }
                }
            })

        # [NEW] 파일 다운로드 및 분석 (try-finally로 정리 보장)
        res = collect_and_split_data(os.getenv("YT_SHORTS_API_KEY"), url, v_id)
        _, storage_path = get_safe_metadata(res)
        
        try:
            video_path = os.path.join(storage_path, "video.mp4")
            print("[/api/video/detect] video_path: ", video_path)
            if not os.path.exists(video_path):
                for f in os.listdir(storage_path):
                    if f.endswith((".mp4", ".webm")):
                        video_path = os.path.join(storage_path, f)
                        break
            
            result = video.analyze_with_gemini_25(video_path)
            if result is None:
                return jsonify({"status": "error", "message": "분석 실패"}), 500
            ai_val, human_val = result

            # [NEW] 결과 데이터 구성
            analysis_data = {
                "video_id": v_id,
                "ai_score": ai_val,
                "human_score": human_val,
                "storage_path": storage_path, # 디버깅용 (나중에 삭제 가능)
            }

            # [NEW] DB 저장 (Partial Update)
            try:
                db_handler.save_analysis_result(analysis_data)
            except Exception as e:
                print(f"⚠️ [DB Error] {e}")

            return jsonify({
                "status": "success",
                "data": {
                    "video_id": v_id,
                    "detection_result": {
                        "avg_fake_score": round(float(ai_val), 4),  # AI로 판정된 프레임들의 평균 점수
                        "avg_real_score": round(float(human_val), 4),  # Real로 판정된 프레임들의 평균 점수
                        "fake_frame_count": 1,
                        "real_frame_count": 1,
                        "total_analyzed_frames": 1
                    }
                }
            })
        finally:
            # 성공/실패 여부와 관계없이 임시 폴더 삭제
            if os.path.exists(storage_path):
                print(f"🗑️ [Cleanup] Deleting temporary files: {storage_path}")
                shutil.rmtree(storage_path)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================

import json
import asyncio
from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# gemini_main.py에서 분석 함수와 기본 프롬프트를 가져옵니다.
from gemini_main import main as gemini_analyze, PROMPT

@app.route('/api/video/transcript', methods=['POST'])
@trace("Route: Get Transcript")
def get_transcript():
    """
    유튜브 URL을 입력받아 자막을 추출
    API 명세: POST /api/video/transcript
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({
            "status": "error",
            "message": "Missing 'url' in request body"
        }), 400

    video_url = data.get('url')

    script_text = get_youtube_transcript2(video_url)
    if not script_text:
        return jsonify({
            "status": "error",
            "message": "자막을 찾을 수 없습니다."
        }), 404

    return jsonify({
        "status": "success",
        "data": script_text
    })


import asyncio

@app.route('/api/video/analyze', methods=['POST'])
@trace("Route: Integrated Video & Site Analysis (Fail-safe)")
def analyze_video():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"status": "error", "message": "Missing 'url' in request body"}), 400

    video_url = data.get('url')
    video_id = get_video_id(video_url)

    async def run_analysis():
        task_transcript = asyncio.to_thread(get_youtube_transcript2, video_url)
        task_site_trace = asyncio.to_thread(run_site_verification, video_url)

        script_text, trust_report = await asyncio.gather(task_transcript, task_site_trace)
        

        if not script_text:
            script_text = "이 영상은 자막을 제공하지 않습니다. 웹사이트 정보와 브랜드명을 기반으로 분석하세요."

        # 2. 통합 정보를 Gemini에게 전달
        from gemini_main import evaluate_with_site_info
        report = await evaluate_with_site_info(script_text, trust_report)
        
        return (script_text, trust_report, report), None

    try:
        result, error = asyncio.run(run_analysis())
        
        # 이제 error는 네트워크 치명적 오류가 아닌 이상 발생하지 않습니다.
        script_text, trust_report, report = result

        try:
            # Gemini 응답이 문자열일 경우 JSON 파싱
            analysis_result = json.loads(report) if isinstance(report, str) else report
        except:
            analysis_result = report

        # DB 저장 시도
        try:
            db_handler.save_analysis_result({
                "video_id": video_id,
                "script_analysis": analysis_result,
                "trust_report": trust_report
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
    step1_res = tracer.analyze(video_url)
    final_link = step1_res.get('landing_page_url')
    
    step2_res = None
    if final_link and "http" in final_link:
        analyzer = BrandTrustAnalyzer(tracer.client)
        step2_res = analyzer.generate_trust_report(
            target_url=final_link,
            product_name=step1_res.get('product_name'),
            brand=step1_res.get('brand')
        )
    return {
        "step1_video_discovery": step1_res,
        "step2_deep_verification": step2_res
    }
    
from youtube_transcript_api.formatters import TextFormatter

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
        
        # 혹시 모를 로직 에러 확인을 위해 단계별 프린트
        # 만약 YouTubeTranscriptApi 자체가 static method만 지원한다면 여기서 터질 수 있음
        # ytt_api = YouTubeTranscriptApi() -> 이 부분 확인 필요
        
        # 1. 표준적인 방법 (static method) 시도
        try:
            print("[DEBUG] Trying YouTubeTranscriptApi.get_transcript (Static Method)...")
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
            print("[DEBUG] Success with static method.")
        except Exception as e_static:
            print(f"[DEBUG] Static method failed: {e_static}")
            print("[DEBUG] Trying original user code (Instance Method)...")
            
            # 2. 기존 유저 코드 (Instance Method)
            ytt_api = YouTubeTranscriptApi()
            transcript = ytt_api.fetch(video_id, languages=languages)
            print("[DEBUG] Success with instance method.")

        # 순수 텍스트로 변환하여 Gemini 분석에 최적화
        print("[DEBUG] Formatting transcript...")
        formatter = TextFormatter()
        formatted_text = formatter.format_transcript(transcript).strip()
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

    # 1. DB 캐시 확인 (중복 분석 방지)
    cached = db_handler.get_analysis_result(v_id)
    if cached and "trust_report" in cached:
        return jsonify({"status": "success", "data": cached["trust_report"], "cached": True})

    try:

        tracer = LinkTracer() 
        
        # Step 1: 영상 분석 및 구매 링크 추적
        # (이 함수 내부에서 download -> analyze -> remove_temp 과정이 한 번에 일어납니다)
        step1_res = tracer.analyze(url) 
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

        # 3. 결과 DB 저장 (Partial Update)
        db_handler.save_analysis_result({"video_id": v_id, "trust_report": final_report})

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