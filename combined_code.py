import os
import sys
sys.path.append(os.path.dirname(__file__))

from yt_shorts import collect_and_split_data, get_video_id, get_or_save_api_key
from code4 import get_youtube_transcript

def combined_function(link):
    # 링크를 입력받아 yt-shorts.py의 코드를 호출하여 데이터를 추출
    api_key = get_or_save_api_key()
    video_id = get_video_id(link)
    if not video_id:
        return "Invalid YouTube URL"
    
    # yt-shorts.py의 collect_and_split_data 호출 (데이터 추출)
    folder_path = collect_and_split_data(api_key, link, video_id)
    
    # 그 후 code4.py의 get_youtube_transcript 호출하여 자막 추출
    transcript = get_youtube_transcript(link)
    
    return transcript

# 사용 예시
if __name__ == "__main__":
    link = input("YouTube 링크를 입력하세요: ").strip()
    output = combined_function(link)
    print("Transcript:", output)