# Sprint Backend - 개발 가이드

## 환경 설정

### 가상환경

이 프로젝트는 **uv**를 사용하여 가상환경을 관리합니다.

```powershell
# 가상환경 활성화
& .\.venv\Scripts\Activate.ps1
```

### PyTorch CUDA 설치

> **중요**: 기본 PyPI에서 설치하면 CPU 전용 PyTorch가 설치됩니다. GPU 추론을 위해서는 반드시 CUDA 버전을 설치해야 합니다.

```powershell
# 기존 CPU 버전 제거
uv pip uninstall torch torchvision --python .venv

# CUDA 12.4 버전 설치 (RTX 2060 등 GPU 지원)
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 --python .venv
```

설치 확인:
```powershell
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

정상 출력 예시:
```
CUDA available: True
GPU: NVIDIA GeForce RTX 2060
```

## 모델

- **NPR 모델** (`models/npr_model/`): 딥페이크 탐지 모델, GPU 추론 지원
