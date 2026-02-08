from flask import Flask, jsonify
from flask_cors import CORS
from utils.profiler import trace, profiler

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
import os
import json
import cv2
import imageio
from yt_shorts import get_video_id, collect_and_split_data, get_or_save_api_key
from models.npr_model.npr_wrapper import NPRDetector

# ==========================================
# 1. 전역 설정 및 모델 로드
# ==========================================
npr_detector = NPRDetector(model_filename="model_epoch_last_3090.pth")

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
        
        # 2. 영상 다운로드(yt-dlp) 없이 메타데이터만 호출 (속도 개선)
        from yt_shorts import get_metadata_only # 새로 만든 함수 임포트
        item = get_metadata_only(api_key, v_id)
        
        if not item:
            return jsonify({"status": "error", "message": "영상을 찾을 수 없습니다."}), 404

        snippet = item.get('snippet', {})
        stats = item.get('statistics', {})

        # 3. 이상적인 명세서(Ideal Spec) 규격에 맞춘 응답 구성 
        return jsonify({
            "status": "success",
            "data": {
                "video_id": v_id, 
                "title": snippet.get("title"),
                "channel_name": snippet.get("channelTitle"), 
                "published_at": snippet.get("publishedAt"), 
                "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"), 
                "view_count": stats.get("viewCount") 
            }
        })
    except Exception as e:
        # 에러 메시지를 구체적으로 확인하기 위해 e 출력
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 3. 딥페이크 탐지 (NPR 원본 로직 적용 + 기존 응답 구조 유지)
# ==========================================

# @app.route('/api/video/detect', methods=['POST'])
@trace("Route: Analyze NPR (Deepfake)")
def detect_deepfake():
    """
    NPR-CVPR2024 원본 추론 로직을 사용하여 
    Real 및 Fake 프레임의 평균 점수를 계산합니다.
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    interval = int(data.get("interval", 20))
    threshold = float(data.get("threshold", 0.5))

    if not url:
        return jsonify({"status": "error", "message": "URL이 필요합니다."}), 400

    try:
        print(f"\n🚀 영상 분석 시작 (점수 평균 계산 모드)") 
        
        v_id = get_video_id(url)
        res = collect_and_split_data(get_or_save_api_key(), url, v_id)
        _, storage_path = get_safe_metadata(res)
        
        video_path = os.path.join(storage_path, "video.mp4")
        if not os.path.exists(video_path):
            for f in os.listdir(storage_path):
                if f.endswith((".mp4", ".webm")):
                    video_path = os.path.join(storage_path, f)
                    break
        
        cap = cv2.VideoCapture(video_path)
        
        # 점수 계산을 위한 변수 초기화
        fake_scores = []
        real_scores = []
        analyzed_frames = 0
        frame_idx = 0

        try:
            if not cap.isOpened():
                raise RuntimeError(f"비디오를 열 수 없음: {video_path}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame is None or frame.size == 0:
                    frame_idx += 1
                    continue

                # Interval마다 분석 수행
                if frame_idx % interval == 0:
                    try:
                        # npr_detector로부터 0~1 사이의 score 획득
                        score = float(npr_detector.predict_image(frame))
                        
                        # threshold 기준으로 Real/Fake 분리하여 리스트에 저장
                        if score > threshold:
                            fake_scores.append(score)
                        else:
                            real_scores.append(score)
                            
                        analyzed_frames += 1
                    except Exception as e:
                        print(f"[WARN] {frame_idx}번 프레임 분석 중 모델 에러: {e}")
                frame_idx += 1

        finally:
            cap.release()

        if analyzed_frames == 0:
            raise RuntimeError("분석된 프레임이 없습니다.")

        # [평균 점수 계산]
        # 리스트가 비어있을 경우(0)를 대비해 처리
        avg_fake_score = sum(fake_scores) / len(fake_scores) if fake_scores else 0.0
        avg_real_score = sum(real_scores) / len(real_scores) if real_scores else 0.0

        print(f"✅ 분석 완료: Fake 평균 {round(avg_fake_score, 4)}, Real 평균 {round(avg_real_score, 4)}")

        return jsonify({
            "status": "success",
            "data": {
                "video_id": v_id,
                "detection_result": {
                    "avg_fake_score": round(avg_fake_score, 4),  # Fake로 판정된 프레임들의 평균 점수
                    "avg_real_score": round(avg_real_score, 4),  # Real로 판정된 프레임들의 평균 점수
                    "fake_frame_count": len(fake_scores),
                    "real_frame_count": len(real_scores),
                    "total_analyzed_frames": analyzed_frames
                }
            }
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 3. 딥페이크 탐지 (Gemini 2.5 Flash 적용)
# ==========================================
import gemini_graph.video as video

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
        res = collect_and_split_data(get_or_save_api_key(), url, v_id)
        _, storage_path = get_safe_metadata(res)
        
        video_path = os.path.join(storage_path, "video.mp4")
        if not os.path.exists(video_path):
            for f in os.listdir(storage_path):
                if f.endswith((".mp4", ".webm")):
                    video_path = os.path.join(storage_path, f)
                    break
        
        ai_val, human_val = video.analyze_with_gemini_25(video_path)

        return jsonify({
            "status": "success",
            "data": {
                "video_id": v_id,
                "detection_result": {
                    "avg_fake_score": round(ai_val, 4),  # AI로 판정된 프레임들의 평균 점수
                    "avg_real_score": round(human_val, 4),  # Real로 판정된 프레임들의 평균 점수
                    "fake_frame_count": 1,
                    "real_frame_count": 1,
                    "total_analyzed_frames": 1
                }
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================

import json
import asyncio
from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# gemini_main.py에서 분석 함수와 기본 프롬프트를 가져옵니다.
from gemini_main import main as gemini_analyze, PROMPT_1

@app.route('/api/video/analyze', methods=['POST'])
@trace("Route: Analyze YouTube (Script-based Analysis)")
def analyze_video():
    """
    유튜브 URL을 입력받아 자막 추출 후 Gemini 분석 결과를 반환
    API 명세: POST /api/video/analyze
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({
            "status": "error",
            "message": "Missing 'url' in request body"
        }), 400

    video_url = data.get('url')
    custom_prompt = data.get('prompt', PROMPT_1)    # 사용자 정의 프롬프트 혹은 기본값
    
    # 1. YouTube Video ID 추출
    try:
        video_id = get_video_id(video_url)
        if not video_id:
            video_id = video_url.split("v=")[-1].split("&")[0]
    except Exception:
        return jsonify({"status": "error", "message": "Invalid YouTube URL format"}), 400

    # 2. 자막 추출 (YouTubeTranscriptApi)
    try:
        script_text = get_youtube_transcript2(video_url)
        if not script_text:
            return jsonify({
                "status": "error",
                "message": "자막을 찾을 수 없습니다."
            }), 404

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"자막을 가져오는데 실패했습니다: {str(e)}"
        }), 500

    # 3. Gemini 분석 (async 함수 호출)
    try:
        # asyncio.run을 사용하여 비동기 분석 함수 실행
        report = asyncio.run(gemini_analyze(custom_prompt, script_text))
        
        # gemini_main에서 반환된 JSON 문자열을 파싱하여 객체로 변환
        try:
            analysis_result = json.loads(report)
        except (TypeError, json.JSONDecodeError):
            analysis_result = report

        return jsonify({
            "status": "success",
            "data": {
                "video_id": video_id,
                "analysis_result": analysis_result
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Gemini 분석 중 오류 발생: {str(e)}"
        }), 500


############## 건드리지 말 것 ##############

if __name__ == '__main__':
    # 참고: MCP 커넥터는 첫 요청 시 Lazy 초기화됩니다 (이벤트 루프 충돌 방지)
    app.run(debug=True, host='0.0.0.0', port=5173)

########################################
