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
# 3. 딥페이크 탐지
# ==========================================
# ==========================================
# 3. 딥페이크 탐지 (NPR 원본 로직 적용 + 기존 응답 구조 유지)
# ==========================================
@app.route('/api/video/detect', methods=['POST'])
@trace("Route: Analyze NPR (Deepfake)")
def detect_deepfake():
    """
    NPR-CVPR2024 원본 추론 로직을 사용함
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    interval = int(data.get("interval", 20))
    threshold = float(data.get("threshold", 0.5))

    if not url:
        return jsonify({"status": "error", "message": "URL이 필요합니다."}), 400

    try:
        print(f"\n🚀 영상 분석 시작 (NPR 원본 로직)") 
        
        # [STEP 1] 영상 추출 및 파일 경로 획득
        v_id = get_video_id(url)
        res = collect_and_split_data(get_or_save_api_key(), url, v_id)
        _, storage_path = get_safe_metadata(res)
        
        video_path = os.path.join(storage_path, "video.mp4")
        if not os.path.exists(video_path):
            for f in os.listdir(storage_path):
                if f.endswith((".mp4", ".webm")):
                    video_path = os.path.join(storage_path, f)
                    break
        
        # [STEP 2] NPR 모델 분석 실행 (안전/견고 버전)
        cap = cv2.VideoCapture(video_path)
        fake_frame_count = 0
        analyzed_frames = 0
        frame_idx = 0

        try:
            if not cap.isOpened():
                raise RuntimeError(f"비디오를 열 수 없음: {video_path}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

            # 코덱 불안정으로 인한 빈 프레임 방어
                if frame is None or frame.size == 0:
                    frame_idx += 1
                    continue

            # Interval마다 분석 및 저장 수행
                if frame_idx % interval == 0:
                # [이미지 저장]
                # [NPR 분석]
                    try:
                        score = float(npr_detector.predict_image(frame))
                        if score > threshold:
                            fake_frame_count += 1
                        analyzed_frames += 1
                    except Exception as e:
                        print(f"[WARN] {frame_idx}번 프레임 분석 중 모델 에러: {e}")
                frame_idx += 1

        finally:
            cap.release()

    # 결과 검증
        if analyzed_frames == 0:
            raise RuntimeError("분석/저장된 프레임이 없습니다. 파일이나 설정을 확인하세요.")

        
        # [STEP 3] AI 생성률(ai_rate) 계산
        ai_rate = (fake_frame_count / analyzed_frames) * 100 if analyzed_frames > 0 else 0.0
        print(f"✅ 분석 완료: 생성률 {round(ai_rate, 2)}%")

        # [STEP 4] 기존 응답 형식 그대로 반환
        return jsonify({
            "status": "success",
            "data": {
                "video_id": v_id,
                "detection_result": {
                    "is_deepfake": ai_rate > 50, # 기존 예시 기준 유지
                    "confidence_score": f"{round(ai_rate, 2)}%",
                    "detected_frames": fake_frame_count,
                    "total_analyzed_frames": analyzed_frames
                }
            }
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

############# 승언 추가 #############
# youtube-transcript-api 패키지 설치
# 주의: 설치 후 커널을 재시작해야 할 수 있습니다 (Kernel -> Restart Kernel)
# pip install youtube-transcript-api 를 터미널에 입력하세요.

import json
from youtube_transcript_api import YouTubeTranscriptApi
from flask import Flask, jsonify
from flask import request

# app = Flask(__name__)

@app.route('/transcript', methods=['POST'])
def get_youtube_transcript():
    """
    유튜브 영상의 자막을 추출하는 함수
    
    Parameters:
    - video_url: 유튜브 영상 URL (예: https://www.youtube.com/watch?v=abcd1234)
    - languages: 원하는 언어 코드 리스트 (예: ['ko', 'en']). None이면 기본 언어 사용
    - save_to_json: JSON 파일로 저장할 경로 (예: 'transcript.json'). None이면 저장하지 않음
    
    Returns:
    - 자막 데이터 리스트 (각 항목: {'text': str, 'start': float, 'duration': float})
    """

    data = request.json
    video_url = data.get('video_url')
    languages = data.get('languages')
    save_to_json = data.get('save_to_json')
    
    if not video_url:
        return jsonify({"status": "error", "message": "video_url is required"}), 400
    
    # YouTube URL에서 video_id 분리
    # 예: https://www.youtube.com/watch?v=abcd1234 -> abcd1234
    video_id = video_url.split("v=")[-1].split("&")[0]

    try:
        # YouTubeTranscriptApi 인스턴스 생성
        ytt_api = YouTubeTranscriptApi()
        
        # 자막 가져오기
        if languages:
            transcript = ytt_api.fetch(video_id, languages=languages)
        else:
            # 언어 지정 없이 자동으로 사용 가능한 자막 선택
            transcript = ytt_api.fetch(video_id)
        
        # JSON 파일로 저장 (옵션)
        if save_to_json:
            with open(save_to_json, 'w', encoding='utf-8') as f:
                json.dump(transcript, f, ensure_ascii=False, indent=4)
            print(f"Transcript saved to {save_to_json}")
        
        return jsonify({"status": "success", "transcript": transcript})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 사용 예시
# if __name__ == "__main__":
#     app.run(debug=True)

# 수정 제안 예시
from youtube_transcript_api.formatters import TextFormatter

def get_youtube_transcript2(video_url, languages=['ko', 'en']):
    from yt_shorts import get_video_id
    video_id = get_video_id(video_url) # 다양한 URL 지원
    if not video_id: return None

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=languages)
        
        # 순수 텍스트로 변환하여 Gemini 분석에 최적화
        formatter = TextFormatter()
        return formatter.format_transcript(transcript).strip()
    except Exception:
        return None


############# 도현 추가 #############

from gemini_main import main as gemini_analyze, PROMPT_1
import asyncio, os

@app.route('/analyze', methods=['POST'])
@trace("Route: Analyze script (Gemini)")
def analyze():
    data = request.get_json()
    if not data or 'script' not in data:
        return jsonify({
            "status": "error",
            "message": "Missing 'script' in request body"
        }), 400
    
    script = data.get('script')
    prompt = data.get('prompt', PROMPT_1)
    
    try:
        # gemini_analyze is an async function, so we run it using asyncio
        report = asyncio.run(gemini_analyze(prompt, script))

        # gemini_main에서 반환된 JSON 문자열을 파싱하여 객체로 변환
        try:
            report_data = json.loads(report)
        except (TypeError, json.JSONDecodeError):
            report_data = report

        return jsonify({
            "status": "success",
            "report": report_data
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

###################################

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

    # 3. AI 분석 (Gemini vs Ollama vs Friendli)
    provider = data.get('provider', 'gemini') # gemini, ollama, or friendli
    model_name = data.get('model')  # Custom model name (optional)
    
    try:
        report = ""
        analysis_result = {}

        if provider == 'friendli':
            # Friendli.ai Serverless API 분석
            from friendli_main import main as friendli_analyze
            
            # Default to DeepSeek-V3.1 if model not specified
            # 지원 모델: exaone, qwen, deepseek (또는 전체 모델명)
            target_model = model_name if model_name else "deepseek-ai/DeepSeek-V3.1"
            
            print(f"🚀 Friendli 분석 시작 (Model: {target_model})")
            report = asyncio.run(friendli_analyze(custom_prompt, script_text, model_name=target_model))

        elif provider == 'ollama':
            # Ollama 분석 (import needs to be lazy or top-level, adding import here for safety/clarity)
            from ollama_main import main as ollama_analyze
            
            # Default to exaone-deep if model not specified for ollama
            target_model = model_name if model_name else "exaone-deep:7.8b"
            
            print(f"🚀 Ollama 분석 시작 (Model: {target_model})")
            report = asyncio.run(ollama_analyze(custom_prompt, script_text, model_name=target_model))
        else:
            # Gemini 분석
            print(f"🚀 Gemini 분석 시작")
            # Gemini currently handles its own model selection inside gemini_main, 
            # but we could potentially pass it if we update gemini_main.
            # For now, we only support changing prompt/script.
            report = asyncio.run(gemini_analyze(custom_prompt, script_text))
        
        # 결과 파싱 (공통 로직)
        try:
            analysis_result = json.loads(report)
        except (TypeError, json.JSONDecodeError):
            analysis_result = report

        return jsonify({
            "status": "success",
            "data": {
                "video_id": video_id,
                "provider": provider,
                "model": model_name if model_name else (provider if provider == 'gemini' else "exaone-deep:7.8b"),
                "analysis_result": analysis_result
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"{provider} 분석 중 오류 발생: {str(e)}"
        }), 500


############## 건드리지 말 것 ##############

if __name__ == '__main__':
    # 참고: MCP 커넥터는 첫 요청 시 Lazy 초기화됩니다 (이벤트 루프 충돌 방지)
    app.run(debug=True, host='0.0.0.0', port=5173)

########################################
