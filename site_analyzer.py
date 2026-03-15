import os
import re
import json
import requests
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google import genai  
from google.genai import types 
from youtube_transcript_api import YouTubeTranscriptApi

load_dotenv()

class LinkTracer:
    def __init__(self):
        self.gemini_key = os.getenv('api_key_grounding')
        self.youtube_api_key = os.getenv('Youtube_API_Key') or os.getenv('YT_SHORTS_API_KEY')
        
        if not self.gemini_key:
            raise ValueError("❌ api_key_grounding가 설정되어 있지 않습니다!")

        self.youtube = build('youtube', 'v3', developerKey=self.youtube_api_key)
        self.client = genai.Client(api_key=self.gemini_key)
    
    def get_comments(self, video_id, max_results=50):
        try:
            request = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=max_results,
                order="relevance"
            )
            response = request.execute()
            comments = [item['snippet']['topLevelComment']['snippet']['textDisplay'] for item in response.get('items', [])]
            return " | ".join(comments) if comments else "댓글 없음"
        except Exception as e:
            print(f"⚠️ [Comment Error] {e}")
            return "댓글 없음"

    def extract_video_id(self, url):
        patterns = [r'shorts/([\w-]+)', r'v=([\w-]+)', r'be/([\w-]+)']
        for pattern in patterns:
            match = re.search(pattern, url)
            if match: return match.group(1)
        return url.split('/')[-1].split('?')[0]
    
    def download_image(self, url):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.content
            return None
        except Exception as e:
            print(f"⚠️ [Image Download Error] {e}")
            return None

    def get_transcript(self, video_id):
        try:
            ytt_api = YouTubeTranscriptApi()
            transcript = ytt_api.fetch(video_id, languages=['ko', 'en'])
            return " ".join(snippet.text for snippet in transcript).strip()
        except Exception:
            return "자막 없음"

    def analyze_with_gemini_text(self, context_info, image_bytes=None, retry_count=0):
        MAX_RETRIES = 0
        # 프롬프트 내용은 그대로 유지 (길이 관계상 생략하지만 코드에는 포함되어야 함)
        prompt = f"""

Role: 마케팅 데이터 추적 및 기업 실사 통합 전문가
Task: 영상 메타데이터와 썸네일을 분석하여 유입 경로(URL)를 찾고, 해당 사이트의 신뢰성을 즉시 검증하십시오

[데이터 정보]
메타 데이터: {context_info}
썸네일 이미지: (사용자가 업로드한 이미지 파일)

[분석 지침]
Step 1. 멀티모달 분석: 메타데이터를 활용하여 브랜드(또는 회사명)와 상품명(또는 서비스명)을 추측하세요.
1. 멀티모달 분석: 메타데이터를 활용하여 브랜드(또는 회사명)와 상품명(또는 서비스명)을 추측하세요. 
 - **중요: 추측할 때 썸네일을 참고하되, 썸네일에 명시적인 로고가 없거나 아예 연관이 없는 텍스트가 포함될 수 있으므로 썸네일로 추측한 내용은 가장 마지막 단계에서 검증하는 용도로만 활용하세요.
 - 메타데이터를 분석할 때 명시적인 정보 뿐만 아니라 맥락을 파악하여 광고가 홍보하는 브랜드와 제품명을 찾아야합니다.
 - [채널명, 영상제목, 영상스크립트, 설명란] 4가지 요소 중 최소 2개 이상에서 공통적으로 언급되거나 밀접한 연관이 있는 키워드에 집중하세요.
 - 데이터 간의 맥락이 동떨어진 경우(예: 의약 제품 광고인데 채널명이 '이스라엘의 비밀'인 경우 등) 해당 채널명은 분석 가중치에서 제외하고, 제품과 직접 관련된 고유명사를 우선순위에 둡니다.

 2. 법인명 기반 역추적 (Entity Identification):
 - 구글 검색을 통해 해당 브랜드의 운영 법인명을 반드시 추출하세요.
 - 검색창 입력 시 제안되는 '자동 완성 법인명'을 반드시 확인하고 그 법인명도 최종 법인명으로 고려하세요.
 - 연관 검색어와 기업 정보를 활용하여 공식 법인명을 파악한 후, 그 법인이 소유한 공식 자사몰 및 상품 상세 페이지를 역추적하십시오.

3. 검색 전략 및 후보군 도출:
 - 확보된 공식 URL을 포함해서, 브랜드/상품명 조합으로 구글 검색 도구를 사용하여 아래 방식들로 찾은 모든 URL 후보군들을 찾아 'landing_page_candidates'를 키로 가지는 리스트에 입력하세요. 
 - 단순히 접속 가능한 URL이 아닌, '브랜드 신뢰도 분석'이 가능한 사이트를 추출해야 합니다.
 - 광고주가 주로 사용하는 호스팅 서비스(아임웹, 카페24, 고도몰 등)의 패턴을 고려하세요. 만약 공식몰 상세페이지를 찾을 수 없다면, 해당 브랜드의 공식 인스타그램 프로필 링크나 페이스북 광고 라이브러리를 검색하여 현재 활성화된 유입 경로를 역추적하세요.
 - 멀티모달 분석 과정에서 추출한 브랜드와 제품명을 검색하세요. (예: '상품명', '브랜드명', '브랜드명 + 상품명', '상품명 + 구매', '브랜드명 + 자사몰')

4. URL 우선순위 (Strict Hierarchy):
 - 1위: 광고를 통해 파악한 정보들과 내용 및 맥락이 가장 일치하는 페이지
 - 2위: 독립 자사물의 단순 도메인, 독립 자사몰의 특정 상품 상세 페이지
 - 3위: 공식 홈페이지 메인 또는 오픈마켓(쿠팡 등) 판매 페이지 /네이버 브랜드스토어/스마트스토어 상세 페이지
 * 존재하지 않는 링크를 추가하는 것은 안됩니다.

5. 노이즈 제거: 커뮤니티 게시글, 유튜브 링크, 뉴스 기사 URL은 후보에서 절대 제외하세요.

6. 응답은 반드시 아래 JSON 형식으로 하며, JSON 이외의 어느 설명이나 텍스트도 포함하지 마세요.

7. 'analysis_case'와 'trust_analysis'와 'review' 항목은 "분석 생략"으로 채우세요.
 

JSON 응답 형식:
 {{
 "brand": "식별된 브랜드명",
 "Corporate Name": "법인명",
 "product_name": "상품명",
 "landing_page_candidates": ["URL1", "URL2", "URL3"],
 "fined_landing_page": "최종적으로 검증된 URL (유효한 링크가 없으면 '유효한 링크 없음'으로 표기)",
 "evidence": "검색 결과의 어떤 정보를 바탕으로 url을 결정했는지 상세 기술",
 "analysis_case": "분석 생략",
 "trust_analysis": "분석 생략",
 "review": "분석 생략"
}}

            """
        
        contents = [prompt]
        if image_bytes:
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

        try:
            # 모델명은 최신 안정화 버전인 gemini-2.0-flash 권장
            response = self.client.models.generate_content(
                model="gemini-2.5-flash", 
                contents=contents,
                config=types.GenerateContentConfig(
                    #tools=[{"google_search": {}}]
                    )
            )

            raw_text = response.text.strip()
            
            # JSON 추출 정규식
            json_pattern = re.compile(r'(\{.*\})', re.DOTALL)
            match = json_pattern.search(raw_text)
            target_str = match.group(1) if match else raw_text

            # [핵심] JSON 로드 시 인코딩 문제 방지를 위해 strict=False 사용
            res_data = json.loads(target_str, strict=False)
            
            if res_data.get('fined_landing_page') == "유효한 링크 없음" and retry_count < MAX_RETRIES:
                print(f"🔄 재시도 중... ({retry_count + 1}/{MAX_RETRIES})")
                return self.analyze_with_gemini_text(context_info, image_bytes, retry_count + 1)
            
            return res_data
            
        except Exception as e:
            print(f"❌ [Gemini API Error] {e}")
            return {"landing_page_candidates": [], "brand": "분석 실패", "evidence": str(e)}

    def analyze(self, url, hint_data=None):
        v_id = self.extract_video_id(url)
        
        if hint_data and hint_data.get('title'):
            print(f"📦 [Cache Hit] DB 메타데이터 사용: {v_id}")
            channel_name = hint_data.get('channel_name')
            title = hint_data.get('title')
            description = hint_data.get('description', '설명 없음')
            thumbnail_url = hint_data.get('thumbnail_url')
        else:
            print(f"🌐 [API Call] 유튜브 API 호출: {v_id}")
            video_res = self.youtube.videos().list(part='snippet', id=v_id).execute()
            if not video_res['items']: raise ValueError("영상을 찾을 수 없습니다.")
            snippet = video_res['items'][0]['snippet']
            channel_name = snippet.get('channelTitle')
            title = snippet.get('title')
            description = snippet.get('description')
            thumbnails = snippet.get('thumbnails', {})
            thumbnail_url = (thumbnails.get('maxres') or thumbnails.get('high') or thumbnails.get('default', {})).get('url')

        image_bytes = self.download_image(thumbnail_url) if thumbnail_url else None
        transcript = self.get_transcript(v_id)
        comments = self.get_comments(v_id)

        context_text = f"채널명: {channel_name}\n영상제목: {title}\n영상설명: {description}\n영상자막: {transcript}\n주요댓글: {comments}"
        
        return self.analyze_with_gemini_text(context_text, image_bytes)