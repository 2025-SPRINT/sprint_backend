# 스프린트 백엔드 API 명세서 (Sprint Backend API Specification)

이 문서는 스프린트 백엔드 서비스의 주요 엔드포인트인 `/extract`와 `/analyze-youtube`에 대한 상세 기술 명세를 제공합니다.

---

## 1. 영상 데이터 추출 및 AI 분석
**엔드포인트**: `POST /extract`  
**설명**: 유튜브 영상을 다운로드하고, YouTube API 및 yt-dlp를 통해 메타데이터를 추출하며, 영상 프레임을 기반으로 AI(NPR 모델) 딥페이크 탐지를 수행합니다.

### 요청 바디 (Request Body)
- `url` (String, 필수): 분석할 유튜브 영상 또는 쇼츠의 전체 URL.

### 응답 구조 (JSON)
- `status` (String): "success" 또는 "error".
- `message` (String): 결과에 대한 간략한 설명.
- `data` (Object):
    - `video_id` (String): 추출된 유튜브 영상 ID.
    - `storage_path` (String): 자산(영상, JSON 등)이 저장된 로컬 폴더 경로.
    - `video_path` (String): 다운로드된 `.mp4` 파일 경로.
    - `thumbnail_path` (String): `thumbnail.jpg` 파일 경로.
    - `ai_analysis` (Object):
        - `analyzed_frames` (Integer): 분석된 총 프레임 수.
        - `ai_detected_frames` (Integer): AI 생성이 탐지된 프레임 수.
        - `ai_generation_rate` (String): AI 생성 비율 백분율 문자열 (예: "15.5%").
    - `api_data` (Object): YouTube API를 통해 수집된 원본 메타데이터.

---

## 2. 유튜브 분석 (Gemini 통합 분석)
**엔드포인트**: `POST /analyze-youtube`  
**설명**: 유튜브 영상에서 자막을 자동으로 추출하고, Gemini AI를 사용하여 스크립트의 신뢰성과 과학적 타당성을 분석합니다.

### 요청 바디 (Request Body)
- `video_url` (String, 필수): 분석할 유튜브 영상의 전체 URL.
- `languages` (Array, 선택): 시도할 언어 코드 리스트 (기본값: `["ko", "en"]`).
- `prompt` (String, 선택): Gemini 분석에 사용할 커스텀 시스템 프롬프트.

### 응답 구조 (JSON)
- `status` (String): "success" 또는 "error".
- `video_id` (String): 추출된 유튜브 영상 ID.
- `report` (Object): Gemini가 생성한 구조화된 분석 보고서 (JSON):
    - `reliability_level` (String): "안전", "주의", "위험" 중 하나.
    - `summary` (String): 분석 결과에 대한 한 줄 요약.
    - `issues` (Array): 식별된 심리적 기만 요소나 의학적 왜곡 사항 리스트.
    - `patent_check` (Object): 언급된 특허 정보의 실제 존재 여부 확인 결과.
    - `evidence` (Array): Google 검색(Grounding)을 통해 확인된 객관적 근거 리스트.
    - `consultation` (String): 소비자를 위한 전문가 조언 및 유의사항.

---

## 공통 에러 응답
실패 시 모든 엔드포인트는 `500` 또는 `400` 상태 코드와 함께 다음 형식을 반환할 수 있습니다:
```json
{
  "status": "error",
  "message": "에러 내용 상세 설명"
}
```
