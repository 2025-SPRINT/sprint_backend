import torch
import torch.nn.functional as F
from PIL import Image
import torchvision.transforms as transforms
import json
import os
import sys

# 현재 폴더를 경로에 추가하여 기존 파일들을 인식하게 함
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

# 실제 폴더 구조에 맞춘 import
# networks 폴더 안의 resnet.py에서 resnet50을 가져옴
from networks.resnet import resnet50 

class NPRDetector:
    def __init__(self, model_filename="NPR.pth"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 가중치 파일 경로 설정 (weights 폴더 안에 있다고 가정)
        model_path = os.path.join(CURRENT_DIR, "weights", model_filename)
        
        # 모델 구조 선언
        self.model = resnet50(num_classes=1)
        
        # 모델 로드
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {model_path}")
            
        state_dict = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()

        # 이미지 전처리 (NPR 논문 설정)
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    def predict(self, image_path):
        """이미지 한 장을 판별하여 결과를 dict(JSON용)로 반환"""
        try:
            img = Image.open(image_path).convert('RGB')
            img_t = self.transform(img).unsqueeze(0).to(self.device)

            with torch.no_grad():
                output = self.model(img_t)
                prob = torch.sigmoid(output).item()
            
            is_fake = prob > 0.5
            result = {
                "module": "NPR_Deepfake_Detector",
                "result": "fake" if is_fake else "real",
                "score": round(prob, 4),
                "is_ai_generated": is_fake
            }
        except Exception as e:
            result = {"module": "NPR_Deepfake_Detector", "error": str(e)}
        
        return result

# 테스트용
if __name__ == "__main__":
    # weights 폴더 안에 실제 파일명이 뭔지 확인 후 넣어주세요
    detector = NPRDetector("model_final.pth") 
    print(detector.predict("sample.jpg"))