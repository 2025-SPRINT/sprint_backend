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
import base64
import re
import gemini_main # 이미 설정된 Gemini 모델 객체
from google import genai
import mediapipe as mp
from google.genai import types
from moviepy import VideoFileClip

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

# MediaPipe 초기화 (전역 설정)
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)


def analyze_audio_ai(video_path):
    print(f"🎙️ 오디오 분석 시작: {video_path}")
    audio_path = video_path.replace(".mp4", ".mp3")
    
    try:
        # 영상에서 오디오 추출
        video = VideoFileClip(video_path)
        if video.audio is None:
            return "0.0"
        
        video.audio.write_audiofile(audio_path, logger=None)
        
        # Gemini 분석
        client = genai.Client(api_key=os.getenv("API_KEY"))
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                "이 오디오의 목소리가 AI로 생성되거나 변조된 것인지 분석해줘. 특히 Google의 오디오 SynthID 워터마크가 있는지 확인하고, AI 목소리일 확률을 0.0에서 1.0 사이의 숫자로만 답변해줘.",
                types.Part.from_bytes(data=audio_data, mime_type='audio/mp3')
            ]
        )
        return response.text
    except Exception as e:
        print(f"오디오 분석 에러: {e}")
        return "0.0"
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

# 2. 그 다음 실제 라우트 함수를 정의합니다.
@app.route('/api/video/detect', methods=['POST'])
@trace("Route: Analyze Gemini with Face Crop")
def detect_deepfake(): # 이 함수 이름이 라우트와 연결됩니다.
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    interval = int(data.get("interval", 40)) 
    threshold = 0.5 

    if not url:
        return jsonify({"status": "error", "message": "URL이 필요합니다."}), 400

    try:
        # [STEP 1] 영상 확보
        v_id = get_video_id(url)
        res = collect_and_split_data(get_or_save_api_key(), url, v_id)
        _, storage_path = get_safe_metadata(res)
        
        video_path = os.path.join(storage_path, "video.mp4")
        if not os.path.exists(video_path):
            for f in os.listdir(storage_path):
                if f.endswith((".mp4", ".webm")):
                    video_path = os.path.join(storage_path, f)
                    break

        # [NEW] 오디오 분석 호출 (이제 위에서 정의했으므로 인식됩니다)
        audio_res_text = analyze_audio_ai(video_path)
        audio_match = re.search(r"0\.\d+|1\.0|0", str(audio_res_text))
        audio_fake_score = float(audio_match.group()) if audio_match else 0.0

        # [STEP 2] 비디오 분석
        cap = cv2.VideoCapture(video_path)
        fake_scores = []
        real_scores = []
        analyzed_frames = 0
        frame_idx = 0
        
        client = genai.Client(api_key=os.getenv("API_KEY"))

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % interval == 0 and analyzed_frames < 10:
                results = face_detection.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if results.detections:
                    detection = results.detections[0]
                    bbox = detection.location_data.relative_bounding_box
                    ih, iw, _ = frame.shape
                    cx, cy = (bbox.xmin + bbox.width / 2) * iw, (bbox.ymin + bbox.height / 2) * ih
                    nw, nh = bbox.width * iw * 1.5, bbox.height * ih * 1.5
                    x1, y1 = max(0, int(cx - nw / 2)), max(0, int(cy - nh / 2))
                    x2, y2 = min(iw, int(cx + nw / 2)), min(ih, int(cy + nh / 2))
                    face_crop = frame[y1:y2, x1:x2]
                    
                    if face_crop.size > 0:
                        _, buffer = cv2.imencode('.jpg', face_crop)
                        prompt = "Analyze this human face. Is it AI-generated (Deepfake) or a real human photograph? Answer with a single float number between 0.0 (Real) and 1.0 (AI Generated)."
                        response = client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents=[
                                types.Part.from_text(text=prompt),
                                types.Part.from_bytes(data=buffer.tobytes(), mime_type='image/jpeg')
                            ]
                        )
                        match = re.search(r"0\.\d+|1\.0|0", response.text)
                        score = float(match.group()) if match else 0.5
                        if score > threshold: fake_scores.append(score)
                        else: real_scores.append(score)
                        analyzed_frames += 1
            frame_idx += 1
        cap.release()

        # [STEP 3] 최종 결과 계산 (기존 명세 유지)
        avg_v_score = sum(fake_scores) / len(fake_scores) if fake_scores else 0.0
        # 비디오 6 : 오디오 4 비율로 혼합
        combined_score = (avg_v_score * 0.6) + (audio_fake_score * 0.4)
        avg_real_score = sum(real_scores) / len(real_scores) if real_scores else 0.0

        return jsonify({
            "status": "success",
            "data": {
                "video_id": v_id,
                "detection_result": {
                    "avg_fake_score": round(combined_score, 4),
                    "avg_real_score": round(avg_real_score, 4),
                    "fake_frame_count": len(fake_scores),
                    "real_frame_count": len(real_scores),
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
    app.run(debug=True, host='127.0.0.1', port=5000)

########################################
