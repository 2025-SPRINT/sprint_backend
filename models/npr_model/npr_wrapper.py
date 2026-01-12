import torch
import cv2
from PIL import Image
import torchvision.transforms as transforms
import os
from networks.resnet import resnet50 

class NPRDetector:
    def __init__(self, model_filename="NPR.pth"):
        # 1. 장치 설정 (GPU/CPU)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 2. 경로 설정
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(current_dir, "weights", model_filename)
        
        # 3. 모델 구조 로드 (ResNet50)
        self.model = resnet50(num_classes=1)
        
        # 4. 가중치 로드
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {model_path}")
            
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.to(self.device)
        self.model.eval()

        # 5. 전처리 설정 (NPR 표준 규격)
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    def predict_image(self, cv2_frame):
        
      #  [수정 포인트] 파일 경로가 아닌, 메모리 상의 이미지(cv2_frame)를 직접 받습니다.
       
        try:
            # OpenCV의 BGR 형식을 PIL의 RGB 형식으로 변환
            color_converted = cv2.cvtColor(cv2_frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(color_converted)
            
            # 전처리 적용
            img_t = self.transform(img).unsqueeze(0).to(self.device)

            with torch.no_grad():
                # 모델 추론
                output = self.model(img_t)
                # 0~1 사이의 확률값(점수) 반환
                prob = torch.sigmoid(output).item()
            
            return prob
        except Exception as e:
            print(f"Prediction Error: {e}")
            return 0.5 # 에러 발생 시 중립적인 점수 반환