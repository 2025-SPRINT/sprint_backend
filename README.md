# Sprint Backend Project

이 프로젝트는 Flask 기반의 API 서버입니다. Python 표준 `venv` 모듈과 `pip`를 사용하여 가상환경 및 의존성을 관리합니다.

## 개발 환경 설정

### 1. 가상환경 생성 및 활성화
프로젝트 루트 디렉토리에서 다음 명령어를 실행합니다.

```bash
# 가상환경 생성 (venv 사용)
python3 -m venv .venv

# 가상환경 활성화 (macOS/Linux)
source .venv/bin/activate

# 가상환경 활성화 (Windows)
.venv\Scripts\activate
```

### 2. 의존성 설치
활성화된 가상환경에 필요한 패키지를 설치합니다.

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 서버 실행

서버를 실행하려면 다음 명령어를 입력하세요.

```bash
python app.py
```

서버가 실행되면 기본적으로 `http://localhost:5000`에서 접속 가능합니다.

## API 엔드포인트
- `GET /`: 서버 연결 확인 (JSON 응답)
- `GET /health`: 서버 상태 확인

## 프로젝트 구조
- `app.py`: Flask 애플리케이션 메인 파일
- `requirements.txt`: 프로젝트 의존성 목록
- `.venv/`: 가상환경 디렉토리 (git 관리 제외)
- `.gitignore`: Git 제외 파일 설정
