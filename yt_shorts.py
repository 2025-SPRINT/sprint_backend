import pandas as pd
from googleapiclient.discovery import build
import re
import os
import yt_dlp
import json
import time
from utils.profiler import trace, profiler

# 1. API 키 설정 및 로드 함수
API_KEY_FILE = 'api_key.txt'

def get_or_save_api_key():
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""

def get_video_id(url):
    patterns = [r'shorts/([\w-]+)', r'v=([\w-]+)', r'youtu.be/([\w-]+)']
    for pattern in patterns:
        match = re.search(pattern, url)
        if match: return match.group(1)
    return None

@trace("YouTube Logic: Collect & Split Data")
def collect_and_split_data(api_key, url, video_id):
    """
    App.js 호환성을 유지하며 필수 데이터만 추출합니다.
    성능 측정(profiler) 로직을 보존합니다.
    """
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # [폴더 생성]
    target_dir = os.path.join(os.getcwd(), f"Extraction_{video_id}")
    os.makedirs(target_dir, exist_ok=True)

    print(f"🚀 [최적화 데이터 추출 시작] ID: {video_id}")

    # --- [1] YouTube API 데이터 수집 (필수 정보만) ---
    start_yt_api = time.perf_counter()
    # App.js의 경로(snippet, statistics, localizations)를 모두 만족시키기 위해 part 유지
    video_raw = youtube.videos().list(
        part="snippet,statistics,localizations", 
        id=video_id
    ).execute()
    profiler.log_manual("YouTube API: Get Video Info", time.perf_counter() - start_yt_api)

    # --- [2] yt-dlp 영상 다운로드 및 썸네일 (AI 분석 필수용) ---
    start_ytdlp = time.perf_counter()
    ydl_opts = {
        'format': 'bv*+ba/best',
        'outtmpl': os.path.join(target_dir, "video.%(ext)s"),
        'merge_output_format': 'mp4',
        'postprocessors': [
            {
             'key': 'FFmpegVideoConvertor',
             'preferedformat': 'mp4',
            }
      ],
      'postprocessor_args': [
        '-c:v', 'libx264',
        '-c:a', 'aac'
      ],
        'writethumbnail': True,
        'quiet': True,
        'noplaylist': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # 영상과 썸네일을 실제로 다운로드 (현석님 AI 분석 및 UX 표시용)
        ydl.extract_info(url, download=True)
        profiler.log_manual("yt-dlp: Extract & Download", time.perf_counter() - start_ytdlp)
        
        # 썸네일 파일명 정리
        for f in os.listdir(target_dir):
            if f.endswith(('.webp', '.png', '.jpg')) and "video" not in f:
                try: 
                    new_path = os.path.join(target_dir, "thumbnail.jpg")
                    if os.path.exists(new_path): os.remove(new_path)
                    os.rename(os.path.join(target_dir, f), new_path)
                except: pass

    # --- [3] 결과물 저장 (불필요한 대용량 JSON 생성 제거) ---
    # App.js 경로: full_data -> video_info -> items[0] -> snippet -> title
    api_combined = {
        "video_info": video_raw, # App.js 연동 핵심
        "status": "success"
    }

    # 파일 1: App.js와 app.py가 공통으로 읽는 필수 메타데이터
    with open(os.path.join(target_dir, "data_api_origin.json"), 'w', encoding='utf-8') as f:
        json.dump(api_combined, f, indent=4, ensure_ascii=False)

    # [수정] 기존의 거대한 data_ytdlp_origin.json 파일 생성 코드는 삭제했습니다.
    # 이제 수백 줄의 반복되는 텍스트 데이터가 생기지 않습니다.

    return target_dir

def extract_shorts():
    api_key = get_or_save_api_key()
    url = input("유튜브 링크를 입력하세요: ").strip()
    v_id = get_video_id(url)
    
    if v_id:
        try:
            result_path = collect_and_split_data(api_key, url, v_id)
            print("\n" + "="*70)
            print(f"✅ 추출 및 최적화 완료!")
            print(f"📂 폴더 위치: {result_path}")
            print(f"📦 생성 파일: video.mp4, thumbnail.jpg, data_api_origin.json")
            print("="*70)
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
    else:
        print("❌ 올바른 유튜브 URL 형식이 아닙니다.")

# yt_shorts.py 파일 하단에 추가

@trace("YouTube Logic: Get Metadata Only")
def get_metadata_only(api_key, video_id):
    """
    영상 다운로드 없이 YouTube Data API만 호출하여 0.5초 내 응답 목표
    """
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # 필수 정보(snippet, statistics)만 요청
    video_raw = youtube.videos().list(
        part="snippet,statistics", 
        id=video_id
    ).execute()
    
    if not video_raw.get('items'):
        return None
        
    return video_raw['items'][0]

if __name__ == "__main__":
    extract_shorts()