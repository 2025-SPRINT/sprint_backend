from flask import Flask, jsonify
from flask_cors import CORS
from utils.profiler import trace, profiler

app = Flask(__name__)
CORS(app) # 모든 origin에 대해 CORS 허용

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
npr_detector = NPRDetector(model_filename="NPR.pth")

def get_safe_metadata(result):
    """result가 경로(str)면 파일을 읽고, 사전(dict)이면 그대로 반환"""
    if isinstance(result, str):
        json_path = os.path.join(result, "data_api_origin.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f), result
        return {}, result
    return result, result.get("storage_path")

# --- 유틸리티: 중앙 크롭 함수 (본질 유지) ---
def center_crop(img, target_size=(224, 224)):
    h, w, _ = img.shape
    min_dim = min(h, w)
    start_x = (w - min_dim) // 2
    start_y = (h - min_dim) // 2
    crop = img[start_y:start_y+min_dim, start_x:start_x+min_dim]
    return cv2.resize(crop, target_size, interpolation=cv2.INTER_AREA)

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
@app.route('/api/video/detect', methods=['POST'])
@trace("Route: Analyze NPR (Deepfake)")
def detect_deepfake():
    """실제 영상을 다운로드하고 NPR 모델로 분석하여 AI생성률 반환"""
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    interval = int(data.get("interval", 5))
    threshold = float(data.get("threshold", 0.5))

    if not url:
        return jsonify({"status": "error", "message": "URL이 필요합니다."}), 400

    try:
        print("\n" + "="*50)
        print("🚀 영상 추출 시작") 
        # [STEP 1] 영상 추출 (기존 본질 유지)
        v_id = get_video_id(url)
        res = collect_and_split_data(get_or_save_api_key(), url, v_id)
        _, storage_path = get_safe_metadata(res)
        
        video_path = os.path.join(storage_path, "video.mp4")
        # 실제 파일 경로 확인 로직
        if not os.path.exists(video_path):
            for f in os.listdir(storage_path):
                if f.endswith((".mp4", ".webm")):
                    video_path = os.path.join(storage_path, f)
                    break
        print(f"📍 분석 실행 경로: {video_path}")

        # [STEP 2] AI 분석 (NPR 모델 실행)
        print(f"🔍 분석 시작(이미지 Center Crop 기반): {video_path}")
        reader = imageio.get_reader(video_path)
        fake_frame_count = 0
        analyzed_frames = 0
        
        for i, frame in enumerate(reader):
            if i % interval != 0: continue
            
            analyzed_frames += 1
            img_crop_rgb = center_crop(frame)
            img_crop_bgr = cv2.cvtColor(img_crop_rgb, cv2.COLOR_RGB2BGR)
            
            score = float(npr_detector.predict_image(img_crop_bgr))
            if score > threshold:
                fake_frame_count += 1
        
        reader.close()
        
        # AI 생성률 계산
        ai_rate = (fake_frame_count / analyzed_frames) * 100 if analyzed_frames > 0 else 0.0
        print(f"✅ 분석 완료: 생성률 {round(ai_rate, 2)}%")
        print("="*50 + "\n")

      
        return jsonify({
            "status": "success",
            "data": {
                "video_id": v_id,
                "detection_result": {
                    "is_deepfake": ai_rate > 50, # 예시 기준
                    "confidence_score": f"{round(ai_rate, 2)}%",
                    "detected_frames": fake_frame_count,
                    "total_analyzed_frames": analyzed_frames
                }
            }
        })

    except Exception as e:
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

@app.route('/analyze-youtube', methods=['POST'])
@trace("Route: Analyze YouTube (Full Flow)")
def analyze_youtube():
    """
    유튜브 URL을 입력받아 자막 추출 후 Gemini 분석 리포트를 반환
    """
    data = request.get_json()
    if not data or 'video_url' not in data:
        return jsonify({
            "status": "error",
            "message": "Missing 'video_url' in request body"
        }), 400

    video_url = data.get('video_url')
    languages = data.get('languages', ['ko', 'en']) # 기본 언어 설정
    custom_prompt = data.get('prompt', PROMPT_1)    # 사용자 정의 프롬프트 혹은 기본값
    
    # 1. YouTube Video ID 추출
    try:
        video_id = video_url.split("v=")[-1].split("&")[0]
    except Exception:
        return jsonify({"status": "error", "message": "Invalid YouTube URL format"}), 400

    # 2. 자막 추출 (YouTubeTranscriptApi)
    try:
        script_text = get_youtube_transcript2(video_url)
        print('#' * 80)
        print(script_text)
        print('#' * 80)

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
            report_data = json.loads(report)
        except (TypeError, json.JSONDecodeError):
            report_data = report

        return jsonify({
            "status": "success",
            "video_id": video_id,
            "report": report_data
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Gemini 분석 중 오류 발생: {str(e)}"
        }), 500


############## 건드리지 말 것 ##############

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)

########################################
