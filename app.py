from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
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
def analyze_npr():
    data = request.get_json()
    video_path = data.get("video_path")
    
    if not video_path or not os.path.exists(video_path):
        return jsonify({"status": "error", "message": "파일을 찾을 수 없습니다."}), 400

    try:
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fake_frame_count = 0
        analyzed_count = 0

        print(f"분석 시작: {video_path} (총 {total_frames} 프레임)")

        # 프레임 저장 폴더
        base_dir = os.path.dirname(video_path)
        ai_dir = os.path.join(base_dir, "frames_ai")
        real_dir = os.path.join(base_dir, "frames_real")

        os.makedirs(ai_dir, exist_ok=True)
        os.makedirs(real_dir, exist_ok=True)


        for i in range(0, total_frames, 10):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            success, frame = cap.read()
            if not success:
                break

            analyzed_count += 1
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_results = face_detection.process(frame_rgb)

            score = 0
            if face_results.detections:
                det = face_results.detections[0]
                bbox = det.location_data.relative_bounding_box
                ih, iw, _ = frame.shape
                x = int(bbox.xmin * iw)
                y = int(bbox.ymin * ih)
                w = int(bbox.width * iw)
                h = int(bbox.height * ih)
                face_img = frame[max(0, y):y+h, max(0, x):x+w]

                if face_img.size > 0:
                    score = npr_detector.predict_image(face_img)
            else:
                score = npr_detector.predict_image(frame)

        frame_name = f"frame_{i:06d}.jpg"

        if score > 0.5:
            fake_frame_count += 1
            cv2.imwrite(os.path.join(ai_dir, frame_name), frame)
        else:
            cv2.imwrite(os.path.join(real_dir, frame_name), frame)
        
        cap.release()
        ai_rate = (fake_frame_count / analyzed_count) * 100 if analyzed_count > 0 else 0
        
        analysis_results = {
            "ai_detected_frames": fake_frame_count,
            "ai_generation_rate": f"{round(ai_rate, 2)}%",
            "analyzed_frames": analyzed_count
        }

        return jsonify({
            "status": "success",
            "analysis_results": analysis_results
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 3. [순호+통합] 데이터 추출 엔드포인트
# ==========================================
@app.route('/extract', methods=['POST'])
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
                
                if npr_data.get("status") == "success":
                    npr_analysis = npr_data.get("analysis_results", {})
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

if __name__ == '__main__':
    # print(get_youtube_transcript2())
    app.run(debug=True, host='0.0.0.0', port=8080)
