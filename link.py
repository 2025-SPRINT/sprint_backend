import os
import yt_dlp
import re
import json
import time
import csv
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google import genai  
from google.genai import types 
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import requests
from prettytable import PrettyTable

load_dotenv()

class LinkTracer:
    def __init__(self):
        self.gemini_key = os.getenv('API_KEY')
        self.youtube_api_key = os.getenv('Youtube_API_Key')
        self.youtube = build('youtube', 'v3', developerKey=self.youtube_api_key)
        self.client = genai.Client(api_key=self.gemini_key)

    def extract_video_id(self, url):
        patterns = [r'shorts/([\w-]+)', r'v=([\w-]+)', r'be/([\w-]+)']
        for p in patterns:
            match = re.search(p, url)
            if match: return match.group(1)
        return url.split('/')[-1].split('?')[0]

    def get_transcript(self, video_id):
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            return TextFormatter().format_transcript(transcript).replace('\n', ' ').strip()
        except: return "자막 없음"

    def get_all_comments(self, video_id):
        """댓글 페이지를 순회하며 가능한 모든 댓글을 추출"""
        comments = []
        try:
            request = self.youtube.commentThreads().list(
                part='snippet', videoId=video_id, maxResults=100, order='relevance'
            )
            while request:
                response = request.execute()
                for item in response['items']:
                    comments.append(item['snippet']['topLevelComment']['snippet']['textDisplay'])
                request = self.youtube.commentThreads().list_next(request, response)
            return " | ".join(comments) if comments else "댓글 없음"
        except: return "댓글 수집 불가(중지됨)"

    def download_video(self, video_url):
        temp_filename = f"temp_{int(time.time())}.mp4"
        ydl_opts = {
            'format': 'bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[ext=mp4]',
            'outtmpl': temp_filename, 'quiet': True, 'no_warnings': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return temp_filename

    def verify_url(self, url):
        try:
            # 브라우저처럼 보이기 위한 더 상세한 헤더 설정
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            }
            # verify=False를 추가하여 SSL 인증서 에러로 인한 차단 방지
            res = requests.get(url, headers=headers, timeout=12, allow_redirects=True, verify=False)
            
            # 403(권한없음)이 뜨더라도 일단 페이지가 존재하면 유효한 것으로 간주할 수 있음
            if 200 <= res.status_code < 400 or res.status_code == 403:
                return True, res.url
            return False, None
        except:
            return False, None

    def analyze(self, url):
        v_id = self.extract_video_id(url)
        video_res = self.youtube.videos().list(part='snippet', id=v_id).execute()
        if not video_res['items']: return None
        
        snippet = video_res['items'][0]['snippet']
        channel_name = snippet['channelTitle']
        title = snippet['title']
        description = snippet['description']
        
        # 1. 텍스트 데이터 취합 (채널명, 제목, 설명, 자막, 전체 댓글)
        context_text = (
            f"[채널명]: {channel_name}\n"
            f"[영상제목]: {title}\n"
            f"[더보기란/설명]: {description}\n"
            f"[자막 내용]: {self.get_transcript(v_id)}\n"
            f"[전체 댓글 내용]: {self.get_all_comments(v_id)}"
        )
        
        # 2. 영상 파일 다운로드
        video_path = self.download_video(url)
        video_file = None
        
        try:
            video_file = self.client.files.upload(file=video_path)
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = self.client.files.get(name=video_file.name)

            prompt = f"""
            당신은 광고 유입 경로를 추적하는 마케팅 데이터 전문가입니다.
            제공된 [영상 파일]과 [메타 데이터]를 심층 분석하여, 브랜드와 상품에 관한 정보가 있는 '소비자 유도 페이지'를 결정하세요.

            [메타 데이터]
            {context_text} 

            [분석 지침]
            1. 멀티모달 분석: 영상 파일과 메타데이터를 활용해 브랜드(또는 회사명)와 제품명(또는 서비스명)을 찾으세요. 
              - 영상을 분석할 땐 시각적 자료와 명시적인 정보 뿐만 아니라 내용과 맥락을 파악하여, 광고가 홍보하는 브랜드와 제품명을 찾아야합니다.
              - 메타데이터를 분석할 때도 명시적인 정보 뿐만 아니라 맥락을 파악하여 광고가 홍보하는 브랜드와 제품명을 찾아야합니다.
              - 뚜렷하고 확실한 근거가 있지 않다면, 하나의 자료만 보지 마세요. 영상과 메타데이터를 모두 분석하여 판단하세요.
              - 영상에 지속적으로 뜨는 브랜드와 로고를 감지하세요. 
              * 영상 속에 예시로 잠시 등장하는 브랜드인지, 설명을 위해 언급된 제품인지, 댓글에서 비교를 위해 언급된 브랜드인지 등에 주의하세요.

            2. 검색 전략: 구글 검색 도구를 사용하여 아래 방식들로 찾은 모든 URL 후보군들(최소 3개 이상)을 찾아 'landing_page_candidates'를 키로 가지는 리스트에 입력하세요. 
              - 광고주가 주로 사용하는 호스팅 서비스(아임웹, 카페24, 고도몰 등)의 패턴을 고려하세요. 만약 공식몰 상세페이지를 찾을 수 없다면, 해당 브랜드의 공식 인스타그램 프로필 링크나 페이스북 광고 라이브러리를 검색하여 현재 활성화된 유입 경로를 역추적하세요.
              - 멀티모달 분석 과정에서 추출한 브랜드와 제품명을 검색하세요. (예: '제품명', '브랜드명', '브랜드명 + 제품명', '제품명 + 구매', '브랜드명 + 자사몰')
              - 절대 하나의 URL만 찾고 멈추지 마세요. 브랜드명과 관련된 모든 도메인 패턴( .kr, .co.kr, .org, .net 등)을 샅샅이 찾아보세요.

            3. URL 우선순위 (Strict Hierarchy):
            - 1위: 식별된 브랜드명이나 상품명이 웹사이트의 정보와 일치하는 페이지 또는 파악된 로고가 동일한 페이지.
            - 2위: 독립 자사물의 단순 도메인(예: brand.co.kr), 독립 자사몰의 특정 상품 상세 페이지 (예: brand.co.kr/products/123)
            - 3위: 공식 홈페이지 메인 또는 오픈마켓(쿠팡 등) 판매 페이지 /네이버 브랜드스토어/스마트스토어 상세 페이지
            * 예시로 제시된 링크 구조에 얽매이지 마세요. 
            * 반드시 구글 검색 도구(Google Search)를 통해 실제로 클릭 가능한 URL임을 확인한 것만 후보군에 넣으세요. 절대 추측해서 URL 구조를 만들어내지 마세요.

            4. 노이즈 제거: 커뮤니티 게시글, 유튜브 링크, 뉴스 기사 URL은 후보에서 절대 제외하세요.

            5. 응답은 반드시 아래 JSON 형식으로 하며, JSON 이외의 어느 설명이나 텍스트도 포함하지 마세요.
            
            JSON 응답 형식:
            {{
            "brand": "식별된 브랜드명",
            "product_name": "제품명",
            "landing_page_candidates": ["URL1", "URL2", "URL3"],
            "search_queries_used": ["사용한 검색어 1", "사용한 검색어 2"],
            "evidence": "영상의 어떤 부분이나 검색 결과의 어떤 정보를 바탕으로 결정했는지 상세 기술"
            }}
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(tools=[{"google_search": {}}])
            )

            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            res_data = json.loads(json_match.group())
            
            # 최종 링크 검증
            final_url = "유효한 링크 없음"
            for candidate in res_data.get('landing_page_candidates', []):
                is_live, real_url = self.verify_url(candidate)
                if is_live:
                    final_url = real_url
                    break
            
            res_data['landing_page_url'] = final_url
            res_data['video_url'] = url
            return res_data

        finally:
            if video_file: self.client.files.delete(name=video_file.name)
            if os.path.exists(video_path): os.remove(video_path)

# (이하 실행 로직 및 저장 코드는 이전과 동일)

if __name__ == "__main__":
    video_dataset = [
        "https://www.youtube.com/shorts/V8QUI8mjy6U",
        "https://www.youtube.com/shorts/cDgCFzE9Eo8",
        "https://youtube.com/shorts/ai_ZF-2y0qw?si=qwR22c1a_TOjBJge",
        "https://youtube.com/shorts/VBxjLx4nxWQ?si=CJ2m-c4WksSUbGzr",
        "https://youtube.com/shorts/7Jhxt1BnbdU?si=4gkwnguCzIiGSsn1",
        "https://youtube.com/shorts/cw45qewNqJU?si=9f6B11THErDJUtwK",
        "https://www.youtube.com/shorts/SO-2qOni-J0",
        "https://www.youtube.com/shorts/YJ_Pu6tXoPw",
        "https://www.youtube.com/shorts/ho4jeQNssGA",
        "https://www.youtube.com/shorts/9U0DEv9wl78",
        "https://www.youtube.com/shorts/2M06ZaHhlY0?si=sUzFwzmaxCU0oWbN",
        "https://www.youtube.com/shorts/nMOaPYFPr2g",
        "https://www.youtube.com/shorts/F5TrpeVZWLY",
        "https://youtube.com/shorts/2ZfwLm5gIbY?si=h7yM-vid4yeFNYRX",
        "https://youtube.com/shorts/1vNvhxCoqik?si=3WedKQV7acR-bTNv"
    ]

    tracer = LinkTracer()
    results = []

    for i, url in enumerate(video_dataset, 1):
        try:
            print(f"--- [{i}/{len(video_dataset)}] 분석 중: {url} ---")
            res = tracer.analyze(url)
            
            if res:
                results.append(res)
                # 텍스트 가공 없이 모든 키값과 데이터를 한 줄씩 출력
                print(f"브랜드: {res.get('brand')}")
                print(f"제품명: {res.get('product_name')}")
                print(f"최종 결정된 URL: {res.get('landing_page_url')}")
                print(f"사용된 검색어: {res.get('search_queries_used')}")
                print(f"Gemini 판단 근거 (전체):")
                print(f"{res.get('evidence')}") # 자르지 않고 전체 출력
                print(f"후보군 리스트: {res.get('landing_page_candidates')}")
                print("-" * 60 + "\n")
                
        except Exception as e:
            print(f"❌ [{i}] 에러 발생: {url}")
            print(f"에러 내용: {e}\n")

    # 최종 결과 요약 (간결하게)
    print("="*30 + " 모든 분석 완료 " + "="*30)
    for r in results:
        print(f"[{r['brand']}] -> {r['landing_page_url']}")