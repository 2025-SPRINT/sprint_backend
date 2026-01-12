from flask import Flask, jsonify

from gemini_main import

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "Hello, World! Flask server is running."
    })

############# 순호 추가 #############



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


############# 승언 추가 #############



############# 도현 추가 #############



###################################

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy"
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
