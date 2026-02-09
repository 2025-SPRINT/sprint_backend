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

서버가 실행되면 기본적으로 `http://localhost:5173`에서 접속 가능합니다.

- `POST /api/video/info`: 유튜브 영상 기본 정보 조회 (Metadata)
- `POST /api/video/detect`: 딥페이크(NPR) 및 Gemini 영상 분석 통합
- `POST /api/video/analyze`: 유튜브 자막 기반 Gemini 심층 분석

## API 테스트 가이드 (CURL)

서버가 실행 중인 상태(`http://localhost:5173`)에서 다음 명령어로 기능을 테스트할 수 있습니다.

### 1. 유튜브 영상 기본 정보 조회 (/api/video/info)
영상 다운로드 없이 메타데이터(제목, 조회수, 썸네일 등)만 빠르게 조회합니다.

#### macOS / Linux
```bash
curl -X POST http://localhost:5173/api/video/info \
     -H "Content-Type: application/json" \
     -d '{"url": "https://www.youtube.com/watch?v=I5u6ATxWXbs"}'
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:5173/api/video/info" `
    -Method Post `
    -ContentType "application/json" `
    -Body '{"url": "https://www.youtube.com/watch?v=I5u6ATxWXbs"}' | ConvertTo-Json -Depth 10
```

### 2. 딥페이크 탐지 및 영상 분석 (/api/video/detect)
영상을 다운로드하여 NPR 모델 및 Gemini 2.5 Flash를 통해 AI 생성 여부(Deepfake)를 분석합니다.

#### macOS / Linux
```bash
curl -X POST http://52.79.88.52/api/video/detect \
     -H "Content-Type: application/json" \
     -d '{"url": "https://www.youtube.com/watch?v=vZ4qxeRFiVE"}'
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:5173/api/video/detect" `
    -Method Post `
    -ContentType "application/json" `
    -Body '{"url": "https://www.youtube.com/watch?v=I5u6ATxWXbs"}' | ConvertTo-Json -Depth 10
```

### 3. 자막 기반 심층 분석 (/api/video/analyze)
유튜브 자막을 자동으로 추출하고 Gemini를 통해 내용을 분석합니다.

#### macOS / Linux
```bash
curl -X POST http://52.79.88.52/api/video/analyze \
     -H "Content-Type: application/json" \
     -d '{"url": "https://www.youtube.com/watch?v=I5u6ATxWXbs"}'
```

#### Windows (PowerShell)
```powershell
# | ConvertTo-Json을 붙이면 생략되는 내용 없이 전체 JSON을 볼 수 있습니다.
Invoke-RestMethod -Uri "http://localhost:5173/api/video/analyze" `
    -Method Post `
    -ContentType "application/json" `
    -Body '{"url": "https://www.youtube.com/watch?v=I5u6ATxWXbs"}' | ConvertTo-Json -Depth 10
```

> [!TIP]
> PowerShell에서 `Invoke-RestMethod` 결과가 중간에 끊겨 보인다면 끝에 `| ConvertTo-Json -Depth 10`을 추가하세요. 응답이 PowerShell 객체로 변환되면서 발생하는 표시상의 생략 현상을 방지해 줍니다.

## 프로젝트 구조
- `app.py`: Flask 애플리케이션 메인 파일
- `requirements.txt`: 프로젝트 의존성 목록 (MediaPipe 0.10.11 고정)
- `.venv/`: 가상환경 디렉토리
- `models/`: NPR 등 AI 모델 관련 파일
- `gemini_main.py`: Gemini API 연동 로직
