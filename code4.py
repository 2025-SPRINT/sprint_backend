# youtube-transcript-api 패키지 설치
# 주의: 설치 후 커널을 재시작해야 할 수 있습니다 (Kernel -> Restart Kernel)
# pip install youtube-transcript-api 를 터미널에 입력하세요.

import json
from youtube_transcript_api import YouTubeTranscriptApi
from flask import Flask, jsonify
from flask import request

app = Flask(__name__)

def get_youtube_transcript(video_url, languages=None, save_to_json=None):
    """
    유튜브 영상의 자막을 추출하는 함수
    
    Parameters:
    - video_url: 유튜브 영상 URL (예: https://www.youtube.com/watch?v=abcd1234)
    - languages: 원하는 언어 코드 리스트 (예: ['ko', 'en']). None이면 기본 언어 사용
    - save_to_json: JSON 파일로 저장할 경로 (예: 'transcript.json'). None이면 저장하지 않음
    
    Returns:
    - 자막 데이터 리스트 (각 항목: {'text': str, 'start': float, 'duration': float})
    """
    # YouTube URL에서 video_id 분리
    # 예: https://www.youtube.com/watch?v=abcd1234 -> abcd1234
    video_id = video_url.split("v=")[-1].split("&")[0]

    try:
        # YouTubeTranscriptApi 인스턴스 생성
        ytt_api = YouTubeTranscriptApi()
        
        # 자막 가져오기
        if languages:
            transcript = ytt_api.fetch(video_id, languages=languages)
        else:
            # 언어 지정 없이 자동으로 사용 가능한 자막 선택
            transcript = ytt_api.fetch(video_id)
        
        # JSON 파일로 저장 (옵션)
        if save_to_json:
            with open(save_to_json, 'w', encoding='utf-8') as f:
                json.dump(transcript, f, ensure_ascii=False, indent=4)
            print(f"Transcript saved to {save_to_json}")
        
        return transcript

    except Exception as e:
        return f"Error: {e}"
## 서버 상태 확인용
@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "Hello, World! Flask server is running."
    })
## YouTube 자막 추출 API 수행
@app.route('/transcript', methods=['POST'])
def get_transcript():
    data = request.json
    video_url = data.get('video_url')
    languages = data.get('languages')
    
    if not video_url:
        return jsonify({"status": "error", "message": "video_url is required"}), 400
    
    try:
        transcript = get_youtube_transcript(video_url, languages=languages)
        if isinstance(transcript, str) and transcript.startswith("Error:"):
            return jsonify({"status": "error", "message": transcript}), 500
        return jsonify({"status": "success", "transcript": transcript})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 사용 예시
if __name__ == "__main__":
    app.run(debug=True)