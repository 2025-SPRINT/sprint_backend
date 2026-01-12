# youtube-transcript-api 패키지 설치
# 주의: 설치 후 커널을 재시작해야 할 수 있습니다 (Kernel -> Restart Kernel)
# !pip install youtube-transcript-api

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

def get_youtube_transcript(video_url, languages=None):
    """
    유튜브 영상의 자막을 추출하는 함수
    
    Parameters:
    - video_url: 유튜브 영상 URL (예: https://www.youtube.com/watch?v=abcd1234)
    - languages: 원하는 언어 코드 리스트 (예: ['ko', 'en']). None이면 기본 언어 사용
    
    Returns:
    - 자막 텍스트 문자열
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
        
        # TextFormatter를 사용하여 텍스트로 변환
        formatter = TextFormatter()
        full_text = formatter.format_transcript(transcript)
        
        return full_text.strip()

    except Exception as e:
        return f"Error: {e}"

# 사용 예시
if __name__ == "__main__":
    # 예시 유튜브 URL
    url = "https://www.youtube.com/watch?v=hN8KFzUuhgk"
    
    # 기본 언어로 자막 추출
    transcript = get_youtube_transcript(url)
    print("=== 기본 자막 ===")
    print(transcript)
    print("\n" + "="*50 + "\n")
    
    # 특정 언어로 자막 추출 (한국어 우선, 없으면 영어)
    transcript_ko = get_youtube_transcript(url, languages=['ko', 'en'])
    print("=== 한국어/영어 자막 ===")
    print(transcript_ko)