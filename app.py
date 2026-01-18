from flask import Flask, jsonify
from utils.profiler import trace, profiler

app = Flask(__name__)

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
###############영상 다운->AI 분석->통합추출###############
from yt_shorts import get_video_id, collect_and_split_data, get_or_save_api_key
import cv2
import mediapipe as mp
import os
import json
from flask import Flask, jsonify, request
from models.npr_model.npr_wrapper import NPRDetector
import imageio

# ==========================================
# 1. 전역 설정 및 모델 로드
# ==========================================
npr_detector = NPRDetector(model_filename="NPR.pth")
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(
    model_selection=1,    
    min_detection_confidence=0.5
)

def make_json_safe(obj):
    """JSON 저장 시 에러 방지를 위한 변환 함수"""
    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [make_json_safe(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)

# ==========================================
# 2. [현석] AI 분석 전용 라우트 (분리된 Step 3)
# ==========================================
@app.route('/analyze/npr', methods=['POST'])
@trace("Route: Analyze NPR (Deepfake)")
def analyze_npr():
    data = request.get_json(silent=True) or {}
    video_path = data.get("video_path")

    if not video_path or not os.path.exists(video_path):
        return jsonify({"status": "error", "message": "파일을 찾을 수 없습니다."}), 400

    try:
        interval = int(data.get("interval", 5))         # N프레임마다 분석
        threshold = float(data.get("threshold", 0.5))    # fake 기준

        print(f"분석 시작(이미지 Center Crop 기반): {video_path}")

        # 저장 폴더 설정
        base_dir = os.path.dirname(video_path)
        ai_dir = os.path.join(base_dir, "frames_ai")
        real_dir = os.path.join(base_dir, "frames_real")
        # 수정 제안: 변수명과 폴더명을 더 직관적으로 변경
        ai_crop_dir = os.path.join(base_dir, "crops_ai")    # faces_ai -> crops_ai
        real_crop_dir = os.path.join(base_dir, "crops_real") # faces_real -> crops_real

        for d in [ai_dir, real_dir, ai_crop_dir, real_crop_dir]:
            os.makedirs(d, exist_ok=True)

        fake_frame_count = 0 
        analyzed_frames = 0 
        score_log = []

        # 코덱 및 환경 호환성을 위해 imageio 사용
        reader = imageio.get_reader(video_path)

        # --- 유틸리티: 중앙 크롭 함수 ---
        def center_crop(img, target_size=(224, 224)):
            h, w, _ = img.shape
            min_dim = min(h, w)
            start_x = (w - min_dim) // 2
            start_y = (h - min_dim) // 2
            
            # 중앙 정사각형 추출 후 모델 입력 사이즈로 리사이즈
            crop = img[start_y:start_y+min_dim, start_x:start_x+min_dim]
            return cv2.resize(crop, target_size, interpolation=cv2.INTER_AREA)
        # -----------------------------

        for i, frame in enumerate(reader):
            if i % interval != 0:
                continue

            if frame is None:
                continue

            # 분석 카운트 증가 (얼굴 검출 단계 없이 바로 분석)
            analyzed_frames += 1

            # 이미지 전처리 (RGB -> BGR 및 중앙 크롭)
            # 모델이 요구하는 특정 사이즈가 있다면 target_size를 수정하세요.
            img_crop_rgb = center_crop(frame, target_size=(224, 224))
            img_crop_bgr = cv2.cvtColor(img_crop_rgb, cv2.COLOR_RGB2BGR)

            # 모델 예측
            # [아이디어 전달] NPR 모델은 업샘플링 아티팩트(고주파 노이즈) 추적이 핵심입니다.
            # 현재처럼 이미지를 224로 리사이즈(축소)하면 보간법 때문에 이 흔적이 뭉개져 성능이 떨어질 수 있습니다.
            # 개선안: 리사이즈 대신 원본 해상도에서 중요한 영역(중앙 등)을 224x224 패치로 '절삭'하여 입력하는 것이 정확도가 더 높을 것입니다.
            score = float(npr_detector.predict_image(img_crop_bgr))
            is_fake = score > threshold

            score_log.append({
                "frame_index": i,
                "score": round(score, 6)
            })

            frame_name = f"frame_{i:06d}.jpg"
            crop_name = f"crop_{i:06d}.jpg"

            # 원본 프레임 및 크롭 이미지 저장
            frame_bgr_to_save = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            if is_fake:
                fake_frame_count += 1
                cv2.imwrite(os.path.join(ai_dir, frame_name), frame_bgr_to_save)
                cv2.imwrite(os.path.join(ai_crop_dir, crop_name), img_crop_bgr)
            else:
                cv2.imwrite(os.path.join(real_dir, frame_name), frame_bgr_to_save)
                cv2.imwrite(os.path.join(real_crop_dir, crop_name), img_crop_bgr)

        reader.close()

        # 스코어 로그 저장
        score_log_path = os.path.join(base_dir, "score_log.json")
        with open(score_log_path, "w", encoding="utf-8") as f:
            json.dump(score_log, f, indent=2, ensure_ascii=False)

        # 결과 계산
        ai_rate = (fake_frame_count / analyzed_frames) * 100 if analyzed_frames > 0 else 0.0

        # 요청하신 3개 키값만 반환
        return jsonify({
            "ai_detected_frames": fake_frame_count,
            "ai_generation_rate": f"{round(ai_rate, 2)}%",
            "analyzed_frames": analyzed_frames
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 3. [순호+통합] 데이터 추출 엔드포인트
# ==========================================
@app.route('/extract', methods=['POST'])
@trace("Route: Extract Video Data")
def extract_video_data():
    data = request.get_json(silent=True)
    if not data or not data.get('url'):
        return jsonify({"status": "error", "message": "요청 바디에 'url'이 없습니다."}), 400

    url = data.get('url')
    api_key = get_or_save_api_key()
    v_id = get_video_id(url)

    if not v_id:
        return jsonify({"status": "error", "message": "유효하지 않은 URL입니다."}), 400

    try:
        # --- [STEP 1] 데이터 수집 및 영상 다운로드 ---
        result = collect_and_split_data(api_key, url, v_id)
        print("DEBUG result:", result)

        if isinstance(result, str):
            storage_path = result
        elif isinstance(result, dict):
            storage_path = result.get("storage_path")
        else:
            raise TypeError(f"결과 타입 이상: {type(result)}")

        # --- [STEP 2] 영상 경로 확보 ---
        video_path = os.path.join(storage_path, "video.mp4")
        if not os.path.exists(video_path):
            for f in os.listdir(storage_path):
                if f.startswith("video") and f.endswith((".mp4", ".webm", ".mkv", ".mov", ".avi")):
                    video_path = os.path.join(storage_path, f)
                    break
        
        print(f"📍 분석 실행 경로: {video_path}")

        # --- [STEP 3] AI 분석 호출 (내부 라우트 호출 형식) ---
        npr_analysis = {}
        if video_path and os.path.exists(video_path):
            # Flask 내부 test_client를 사용하여 다른 라우트 호출
            with app.test_client() as client:
                npr_response = client.post('/analyze/npr', json={"video_path": video_path})
            npr_data = npr_response.get_json() or {}

            # ✅ analyze_npr가 이제 3개 필드만 반환하므로, 그 3개가 있으면 성공으로 간주
            required = ("ai_detected_frames", "ai_generation_rate", "analyzed_frames")
            if all(k in npr_data for k in required):
                npr_analysis = npr_data
            else:
                npr_analysis = {"error": "AI 분석 라우트 호출 실패", "detail": npr_data}
        else:
            npr_analysis = {"message": "영상 파일을 찾을 수 없어 분석을 건너뛰었습니다."}

        # --- [STEP 4] 데이터 통합 및 최종 저장 ---
        api_data = {}
        api_json_file = os.path.join(storage_path, "data_api_origin.json")
        if os.path.exists(api_json_file):
            with open(api_json_file, "r", encoding="utf-8") as f:
                api_data = json.load(f)

        final_integrated_data = {
            "video_id": v_id,
            "storage_path": storage_path,
            "video_path": video_path,
            "api_data": api_data,
            "ai_analysis": npr_analysis,
            "thumbnail_path": os.path.join(storage_path, "thumbnail.jpg")
        }
        
        final_integrated_data = make_json_safe(final_integrated_data)

        # 통합 JSON 저장
        integrated_json_path = os.path.join(storage_path, "data_api_integrated.json")
        with open(integrated_json_path, 'w', encoding='utf-8') as f:
            json.dump(final_integrated_data, f, indent=4, ensure_ascii=False, default=str)

        # 원본 JSON에 리포트 추가
        if os.path.exists(api_json_file):
            api_data["ai_analysis_report"] = npr_analysis
            with open(api_json_file, 'w', encoding='utf-8') as f:
                json.dump(api_data, f, indent=4, ensure_ascii=False, default=str)

        return jsonify({
            "status": "success",
            "message": "수집 및 분석이 모두 완료되었습니다.",
            "data": final_integrated_data
        })

    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
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
