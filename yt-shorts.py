import pandas as pd
from googleapiclient.discovery import build
import re
import os
import yt_dlp
import json
from datetime import datetime

# 1. API 키 설정 및 로드 함수
API_KEY_FILE = 'api_key.txt'

def get_or_save_api_key():
    """API 키가 있으면 읽어오고, 없으면 입력받아 저장합니다."""
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    else:
        api_key = input("YouTube API 키를 입력해주세요: ").strip()
        with open(API_KEY_FILE, 'w', encoding='utf-8') as f:
            f.write(api_key)
        return api_key

def get_video_id(url):
    """유튜브 URL에서 비디오 고유 ID를 추출합니다."""
    patterns = [r'shorts/([\w-]+)', r'v=([\w-]+)', r'youtu.be/([\w-]+)']
    for pattern in patterns:
        match = re.search(pattern, url)
        if match: return match.group(1)
    return None

def collect_and_split_data(api_key, url, video_id):
    """API 데이터와 yt-dlp 데이터를 각각 추출하여 개별 JSON으로 저장합니다."""
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # [폴더 생성] 고유 ID 기반으로 저장 폴더 생성
    target_dir = os.path.join(os.getcwd(), f"Extraction_{video_id}")
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    print(f"🚀 [데이터 전수 추출 시작] ID: {video_id}")

    # --- [1] YouTube API 데이터 수집 ---
    # 1-1. 영상 상세 정보 (Snippet, Statistics 등 모든 Part)
    video_raw = youtube.videos().list(
        part="snippet,statistics,contentDetails,status,topicDetails,recordingDetails,liveStreamingDetails,localizations,player",
        id=video_id
    ).execute()

    # 1-2. 댓글 정보 (최대 100개 원본)
    try:
        comments_raw = youtube.commentThreads().list(
            part="snippet,replies",
            videoId=video_id,
            maxResults=100,
            order="relevance"
        ).execute()
    except Exception as e:
        comments_raw = {"error": f"댓글 수집 불가: {str(e)}"}

    # 1-3. 자막 목록 정보 (메타데이터)
    try:
        captions_raw = youtube.captions().list(
            part="snippet",
            videoId=video_id
        ).execute()
    except Exception as e:
        captions_raw = {"error": f"자막 목록 수집 불가: {str(e)}"}

    # --- [2] yt-dlp 데이터 수집 및 영상 다운로드 ---
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': os.path.join(target_dir, "video.%(ext)s"),
        'writethumbnail': True,
        'quiet': True,
        'noplaylist': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ytdlp_raw_info = ydl.extract_info(url, download=True)
        # 썸네일 파일명 정리 (확장자 무관하게 thumbnail.jpg로 변경)
        for f in os.listdir(target_dir):
            if f.endswith(('.webp', '.png', '.jpg')) and "video" not in f:
                try: 
                    os.rename(os.path.join(target_dir, f), os.path.join(target_dir, "thumbnail.jpg"))
                except: 
                    pass

    # --- [3] 결과물 개별 JSON 파일로 저장 ---
    # 파일 1: YouTube API 종합 원본
    api_combined = {
        "video_info": video_raw,
        "comments": comments_raw,
        "captions": captions_raw
    }
    with open(os.path.join(target_dir, "data_api_origin.json"), 'w', encoding='utf-8') as f:
        json.dump(api_combined, f, indent=4, ensure_ascii=False)

    # 파일 2: yt-dlp 메타데이터 원본 (기술 스펙 등)
    with open(os.path.join(target_dir, "data_ytdlp_origin.json"), 'w', encoding='utf-8') as f:
        json.dump(ytdlp_raw_info, f, indent=4, ensure_ascii=False)

    return target_dir

def extract_shorts():
    api_key = get_or_save_api_key()
    url = input("유튜브/쇼츠 링크를 입력하세요: ").strip()
    v_id = get_video_id(url)
    
    if v_id:
        try:
            result_path = collect_and_split_data(api_key, url, v_id)
            print("\n" + "="*70)
            print(f"✅ 모든 데이터 분리 저장 완료!")
            print(f"📂 폴더 위치: {result_path}")
            print(f"1️⃣ YouTube API 원본: data_api_origin.json")
            print(f"2️⃣ yt-dlp 원본: data_ytdlp_origin.json")
            print(f"3️⃣ 멀티미디어: video.mp4 / thumbnail.jpg")
            print("="*70)
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
    else:
        print("❌ 올바른 유튜브 URL 형식이 아닙니다.")

if __name__ == "__main__":
    extract_shorts()