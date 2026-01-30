#pip install opencv-python mediapipe 해야함 오류 나면 아래 두 줄 다시 실행
#uv pip uninstall -y mediapipe
#uv pip install -U --force-reinstall --no-cache-dir mediapipe==0.10.21

#가상환경 만들고, 폴더에 영상 넣고, 가장 아랫줄에 영상제목 입력하고 python face_extract.py 실행
import cv2
import mediapipe as mp
import os

def extract_faces_to_png(video_path, output_dir):
    # 1. 폴더 생성
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 2. MediaPipe 초기화
    mp_face_detection = mp.solutions.face_detection
    face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)

    cap = cv2.VideoCapture(video_path)
    
    frame_count = 0
    saved_count = 0
    interval = 1  # 10프레임마다 분석

    print(f"분석 시작: {video_path}")

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        if frame_count % interval == 0:
            ih, iw, _ = frame.shape
            # BGR을 RGB로 변환하여 분석
            results = face_detection.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            if results.detections:
                # 수정된 좌표 계산 로직
                for i, detection in enumerate(results.detections):
                    bbox = detection.location_data.relative_bounding_box
                    # 1. 중심점과 원래 크기 계산
                    cx, cy = (bbox.xmin + bbox.width / 2) * iw, (bbox.ymin + bbox.height / 2) * ih
                    bw, bh = bbox.width * iw, bbox.height * ih
                    
                    # 2. Scale 적용 (RetinaFace와 동일하게 1.3배 이상 권장)
                    scale = 1.5 
                    nw, nh = bw * scale, bh * scale
                    
                    # 3. 새로운 좌표 계산 (이미지 범위를 벗어나지 않게)
                    x1, y1 = int(cx - nw / 2), int(cy - nh / 2)
                    x2, y2 = int(cx + nw / 2), int(cy + nh / 2)
                    
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(iw, x2), min(ih, y2)

                    face_crop = frame[y1:y2, x1:x2]
                    # ... 이후 저장 로직 동일

                    if face_crop.size > 0:
                        # PNG로 저장 (파일명에 프레임 번호와 순번 포함)
                        save_name = f"face_F{frame_count:05d}_N{i}.png"
                        save_path = os.path.join(output_dir, save_name)
                        
                        # cv2.imwrite는 확장자가 .png면 알아서 PNG로 저장합니다.
                        cv2.imwrite(save_path, face_crop)
                        saved_count += 1
                
                print(f"프레임 {frame_count}: 얼굴 추출 완료")

        frame_count += 1

    cap.release()
    face_detection.close()
    print(f"--- 작업 완료 ---")
    print(f"총 추출된 얼굴 이미지 수: {saved_count}")

# 실행
extract_faces_to_png('영상제목.mp4', 'extracted_faces_png')