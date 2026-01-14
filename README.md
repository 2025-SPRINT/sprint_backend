# Sprint Backend Project

이 프로젝트는 Flask 기반의 API 서버입니다. `uv`를 사용하여 프로젝트 환경 및 의존성을 관리합니다.

> [!IMPORTANT]
> MediaPipe의 `solutions` API 호환성을 위해 **Python 3.11** 사용이 필수적입니다. (Python 3.12+ 에서는 해당 API가 제거되었습니다.)

## 개발 환경 설정

### 1. Python 3.11 설치 및 가상환경 생성

#### 옵션 A: `uv` 사용 (권장)
```bash
# Python 3.11 설치 및 가상환경 생성
uv venv --python 3.11

# 가상환경 활성화 (macOS/Linux)
source .venv/bin/activate
```

#### 옵션 B: 표준 `venv` 사용
Python 3.11이 시스템에 설치되어 있어야 합니다.
```bash
# 가상환경 생성
python3.11 -m venv .venv

# 가상환경 활성화 (macOS/Linux)
source .venv/bin/activate

# 가상환경 활성화 (Windows)
.venv\Scripts\activate
```

### 2. 의존성 설치

#### 옵션 A: `uv` 사용
```bash
uv pip install -r requirements.txt
```

#### 옵션 B: 표준 `pip` 사용
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 서버 실행

서버를 실행하려면 다음 명령어를 입력하세요.

```bash
python app.py
```

또는 `uv run`을 사용할 수 있습니다.
```bash
uv run app.py
```

서버가 실행되면 기본적으로 `http://localhost:8080`에서 접속 가능합니다.

## API 엔드포인트
- `GET /`: 서버 연결 확인 (JSON 응답)
- `GET /health`: 서버 상태 확인
- `POST /analyze/npr`: AI 광고 탐지 (NPR 모델)
- `POST /analyze`: Gemini 기반 스크립트 분석

## 프로젝트 구조
- `app.py`: Flask 애플리케이션 메인 파일
- `requirements.txt`: 프로젝트 의존성 목록 (MediaPipe 0.10.11 고정)
- `.venv/`: 가상환경 디렉토리
- `models/`: NPR 등 AI 모델 관련 파일
- `gemini_main.py`: Gemini API 연동 로직
