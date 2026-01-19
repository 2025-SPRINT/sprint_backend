# 이상적인 스프린트 백엔드 API 명세서 (Ideal API Specification)

현재의 병목 현상(영상 다운로드, AI 분석 대기 시간)을 해결하기 위해, **"즉시 응답 가능한 데이터"**와 **"시간이 걸리는 데이터"**를 분리하여 설계했습니다.
모든 API의 요청 파라미터는 `url`로, 응답 데이터의 키 이름은 일관성 있게 통일했습니다.

---

## 1. 기본 영상 정보 조회 (Fast)
**엔드포인트**: `POST /api/video/info`  
**목적**: UI 렌더링에 필요한 기본 정보를 가장 빠르게 반환합니다 (0.5초 이내). 사용자는 분석이 진행되는 동안 이 정보를 먼저 보게 됩니다.

### 요청 (Request)
```json
{
  "url": "https://www.youtube.com/watch?v=I5u6ATxWXbs"
}
```

### 응답 (Response)
```json
{
  "status": "success",
  "data": {
    "video_id": "I5u6ATxWXbs",
    "title": "국내최초 먹는 성장인자 IGF-1...",
    "channel_name": "엄마를 위한 지식",
    "published_at": "2025-10-11T12:36:41Z",
    "thumbnail_url": "https://i.ytimg.com/vi/I5u6ATxWXbs/hqdefault.jpg",
    "duration": "PT1M35S",
    "view_count": "6061461"
  }
}
```

---

## 2. 스크립트 기반 심층 분석 (Slow - Text processing)
**엔드포인트**: `POST /api/video/analyze`  
**목적**: 자막을 추출하고 Gemini를 통해 내용을 분석합니다. 영상 다운로드가 필요 없어 비교적 빠르지만(3~10초), 메타데이터보다는 느립니다.

### 요청 (Request)
```json
{
  "url": "https://www.youtube.com/watch?v=I5u6ATxWXbs",
  "prompt": "Custom prompt if needed..."
}
```

### 응답 (Response)
```json
{
  "status": "success",
  "data": {
    "video_id": "I5u6ATxWXbs",
    "analysis_result": {
      "reliability_level": "주의",
      "summary": "과장된 의학적 주장이 포함되어 있습니다.",
      "issues": ["검증되지 않은 특허 언급", "공포 마케팅"],
      "expert_consultation": "전문의와 상의가 필요합니다."
    }
  }
}
```

---

## 3. 딥페이크 탐지 (Very Slow - Video processing)
**엔드포인트**: `POST /api/video/detect`  
**목적**: 실제 영상을 다운로드하고 프레임 단위로 AI 모델(NPR)을 돌려 딥페이크 여부를 판단합니다. 가장 시간이 오래 걸립니다(30초+).

### 요청 (Request)
```json
{
  "url": "https://www.youtube.com/watch?v=I5u6ATxWXbs"
}
```

### 응답 (Response)
```json
{
  "status": "success",
  "data": {
    "video_id": "I5u6ATxWXbs",
    "detection_result": {
      "is_deepfake": true,
      "confidence_score": "85.5%",
      "detected_frames": 42,
      "total_analyzed_frames": 564,
      "evidence_image_url": "/static/captures/crop_000123.jpg"
    }
  }
}
```

---

## 🛑 변경된 설계의 핵심 포인트

1.  **책임 분리 (Separation of Concerns)**
    *   `/info`: YouTube Data API만 호출 (초고속)
    *   `/analyze`: 자막 API + Gemini 호출 (중간 속도)
    *   `/detect`: yt-dlp 다운로드 + PyTorch 모델 추론 (느림)

2.  **통일된 인터페이스**
    *   모든 요청은 `{ "url": "..." }` 하나만 보내면 됩니다.
    *   모든 응답은 `data` 객체 안에 결과를 담습니다.
    *   영상 ID는 `video_id`로 통일했습니다.

3.  **프론트엔드 최적화 전략**
    *   페이지 진입 시 `/info`, `/analyze`, `/detect` 세 개를 동시에 호출(`Promise.all` 혹은 개별 호출)합니다.
    *   `/info`가 즉시 오면 썸네일과 제목을 먼저 띄워 **"체감 로딩 시간"을 없앱니다.**
    *   이후 `/analyze`와 `/detect` 결과가 도착하는 대로 UI에 스켈레톤(Skeleton)을 없애고 내용을 채워 넣습니다.
