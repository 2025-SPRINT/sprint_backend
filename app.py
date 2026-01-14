from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "Hello, World! Flask server is running."
    })

############# 순호 추가 #############

@app.route('/extract', methods=['POST'])
def extract_video_data():
    data = request.json
    url = data.get('url')
    api_key = get_or_save_api_key()
    v_id = get_video_id(url)

    if not v_id:
        return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400

    try:
        # 1. 순호님이 영상을 저장하고 그 폴더 경로를 받음
        result_path = collect_and_split_data(api_key, url, v_id)
       
        # 4. 최종 결과 반환
        return jsonify({
            "status": "success",
            "video_id": v_id,
            "storage_path": result_path,
            "files": ["data_api_origin.json", "data_ytdlp_origin.json", "video.mp4", "thumbnail.jpg"],

        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


############# 현석 추가 #############
#일단 from import부분도 내쪽에서 필요한거 아래에 적어놈 나중에 다 위로 보내야함
import cv2
import mediapipe as mp
import os
from flask import Flask, jsonify, request
from models.npr_model.npr_wrapper import NPRDetector

# 서버가 켜질 때 딱 한 번만 실행되어 메모리에 올라갑니다.
npr_detector = NPRDetector(model_filename="NPR.pth")

# MediaPipe 얼굴 인식 설정
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(
    model_selection=1,    
    min_detection_confidence=0.5
)

@app.route('/analyze/npr', methods=['POST'])
def analyze_npr():
    # 사용자가 보낸 JSON 데이터에서 영상 경로 추출
    data = request.json
    video_path = data.get("video_path")
    
    if not video_path or not os.path.exists(video_path):
        return jsonify({"status": "error", "message": "파일을 찾을 수 없습니다."}), 400

    # 영상 열기
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    fake_frame_count = 0  # AI 흔적이 발견된 프레임 수
    analyzed_count = 0    # 실제로 분석한 총 프레임 수

    print(f"분석 시작: {video_path} (총 {total_frames} 프레임)")

    # [2. 분석 로직: 10프레임마다 1장 추출]
    for i in range(0, total_frames, 10):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        success, frame = cap.read()
        if not success:
            break
        
        analyzed_count += 1
        
        # MediaPipe를 위해 BGR에서 RGB로 변환
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_detection.process(frame_rgb)
        
        score = 0
        # 얼굴이 발견된 경우
        if results.detections:
            # 가장 먼저 발견된(보통 가장 큰) 얼굴 영역 추출
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            ih, iw, _ = frame.shape
            
            # 좌표 계산 및 이미지 범위 제한
            x, y, w, h = int(bbox.xmin * iw), int(bbox.ymin * ih), int(bbox.width * iw), int(bbox.height * ih)
            face_img = frame[max(0, y):y+h, max(0, x):x+w]
            
            if face_img.size > 0:
                # 얼굴 부분만 모델에 전달
                score = npr_detector.predict_image(face_img)
        else:
            # 얼굴이 발견되지 않으면 전체 화면 분석 (AI 광고 특성 반영)
            score = npr_detector.predict_image(frame)

        # 개별 프레임의 AI 확률이 0.5를 넘으면 가짜(AI 생성)로 카운트
        if score > 0.5:
            fake_frame_count += 1

    cap.release()

    # [3. 최종 AI 생성률 계산]
    ai_generation_rate = (fake_frame_count / analyzed_count) * 100 if analyzed_count > 0 else 0

    # 결과 반환 
    return jsonify({
        "module": "AI_AD_Detector_NPR",
        "status": "success",
        "video_info": {
            "path": video_path,
            "total_video_frames": total_frames,
            "analyzed_frames": analyzed_count
        },
        "analysis_results": {
            "ai_detected_frames": fake_frame_count,
            "ai_generation_rate": f"{round(ai_generation_rate, 2)}%"
        }
    })

########################################
video_path = os.path.join(result_path, "video.mp4")
@app.route('/extract', methods=['POST'])
def extract_video_data():
    data = request.json
    url = data.get('url')
    api_key = get_or_save_api_key()
    v_id = get_video_id(url)

    if not v_id:
        return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400

    try:
        # 1. 순호님이 영상을 저장하고 그 폴더 경로를 받음
        result_path = collect_and_split_data(api_key, url, v_id)
        
        # 2. 현석님 코드에서 필요한 '정확한 비디오 파일 경로' 생성
        # result_path(폴더) + "video.mp4"(파일명)
        video_path = os.path.join(result_path, "video.mp4")
        
        # 3. 현석님의 분석 함수 호출 (생성한 video_path를 인자로 전달)
        # 현석님 코드의 def analyze_npr(path = None): 이 이 값을 받게 됩니다.
        npr_response = analyze_npr(path=video_path)
        npr_result = npr_response.get_json()

        # 4. 최종 결과 반환
        return jsonify({
            "status": "success",
            "video_id": v_id,
            "storage_path": result_path,
            "files": ["data_api_origin.json", "data_ytdlp_origin.json", "video.mp4", "thumbnail.jpg"],
            # 현석님의 분석 결과 중 필요한 부분만 추출해서 추가
            "ai_analysis": npr_result.get("analysis_results")
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
        return jsonify({
            "status": "success",
            "report": report
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
        
        return jsonify({
            "status": "success",
            "video_id": video_id,
            "report": report
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Gemini 분석 중 오류 발생: {str(e)}"
        }), 500

if __name__ == '__main__':
    # print(get_youtube_transcript2())
    app.run(debug=True, host='0.0.0.0', port=8080)
