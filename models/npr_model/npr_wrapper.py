import torch
import torch.nn as nn
from torch.nn import functional as F
from torchvision import transforms
from torchvision.models import resnet50
import numpy as np
import os
import random
from PIL import Image
from collections import OrderedDict
from copy import deepcopy
import cv2

# 1. 시드 고정 (완벽 재현용)
def seed_torch(seed=1029):
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed) 
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.enabled = False

seed_torch(100)

class NPRDetector:
    def __init__(self, model_filename="model_epoch_last_3090.pth"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 2. 모델 구조 정의 (Layer 3, 4 제거)
        self.model = resnet50()
        self.model.fc1 = nn.Linear(512, 1)
        self.model.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=2, padding=1, bias=False)
        del self.model.layer3, self.model.layer4, self.model.fc
        
        self.model.to(self.device)

        # 3. 가중치 로드 로직 (체크포인트 대응)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(current_dir, "weights", model_filename)
        
        if os.path.exists(model_path):
            checkpoint = torch.load(model_path, map_location=self.device)
            
            # 체크포인트가 딕셔너리 형태일 경우 대응
            state_dict = checkpoint['model'] if isinstance(checkpoint, dict) and 'model' in checkpoint else checkpoint
            
            # OrderedDict를 사용하여 레이어 이름 매핑 (module. 접두사 제거)
            new_state_dict = OrderedDict()
            for k, v in state_dict.items():
                name = k[7:] if k.startswith('module.') else k
                new_state_dict[name] = v
            
            # 복사본을 만들어 안전하게 로드 (deepcopy가 필요한 경우 대비)
            safe_state_dict = deepcopy(new_state_dict)
            
            # 모델에 주입
            try:
                self.model.load_state_dict(safe_state_dict, strict=True)
                print(f"✅ NPR 로컬 모델 로드 완료")
            except Exception as e:
                print(f"❌ 로드 에러 발생: {e}")
                # 만약 에러가 난다면 strict=False로 시도해서 어느 레이어가 안 맞는지 확인해보세요.
                # self.model.load_state_dict(safe_state_dict, strict=False)

        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

    def interpolate(self, img, factor):
        return F.interpolate(
            F.interpolate(img, scale_factor=factor, mode='nearest', recompute_scale_factor=True), 
            scale_factor=1/factor, mode='nearest', recompute_scale_factor=True
        )

    def predict_image(self, cv2_frame):
        try:
    # 1) BGR -> RGB (원본과 동일하게 PIL RGB)
            img_rgb = cv2.cvtColor(cv2_frame, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb).convert("RGB")
            img_t = self.transform(img_pil).unsqueeze(0).to(self.device)  # (1,C,H,W), float32

    # 2) 원본과 동일한 홀수 차원 절삭
            _, c, h, w = img_t.shape
            if h % 2 == 1:
                img_t = img_t[:, :, :-1, :]
            if w % 2 == 1:
                img_t = img_t[:, :, :, :-1]

    # 3) NPR 입력
            npr = img_t - self.interpolate(img_t, 0.5)

            with torch.no_grad():
                x = self.model.conv1(npr * 2.0/3.0)
                x = self.model.bn1(x)
                x = self.model.relu(x)
                x = self.model.maxpool(x)
                x = self.model.layer1(x)
                x = self.model.layer2(x).mean(dim=(2, 3), keepdim=False)
                x = self.model.fc1(x)
                prob = torch.sigmoid(x).item()

            return prob

        except Exception as e:
            print(f"⚠️ Prediction Error: {e}")
            return 0.5