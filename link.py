import os
import yt_dlp
import re
import json
import time
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google import genai  
from google.genai import types 
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import requests

load_dotenv()

class LinkTracer:
    def __init__(self):
        self.gemini_key = os.getenv('API_KEY')
        self.youtube_api_key = os.getenv('Youtube_API_Key')
        
        if not self.gemini_key:
            raise ValueError("❌ .env 파일에 'API_KEY'가 설정되어 있지 않습니다!")

        self.youtube = build('youtube', 'v3', developerKey=self.youtube_api_key)
        self.client = genai.Client(api_key=self.gemini_key)

    def extract_video_id(self, url):
        patterns = [r'shorts/([\w-]+)', r'v=([\w-]+)', r'be/([\w-]+)']
        for pattern in patterns:
            match = re.search(pattern, url)
            if match: return match.group(1)
        return url.split('/')[-1].split('?')[0]

    def get_transcript(self, video_id):
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            return TextFormatter().format_transcript(transcript).replace('\n', ' ').strip()
        except: return "자막 없음"

    def get_comments(self, video_id):
        try:
            res = self.youtube.commentThreads().list(
                part='snippet', videoId=video_id, maxResults=5, order='relevance'
            ).execute()
            comments = [item['snippet']['topLevelComment']['snippet']['textDisplay'] for item in res['items']]
            return " | ".join(comments)
        except: return "댓글 비활성화 또는 없음"

    def download_video(self, video_url):
        temp_filename = f"temp_{int(time.time())}.mp4"
        ydl_opts = {
            'format': 'bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': temp_filename,
            'quiet': True,
            'overwrites': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return temp_filename

    def verify_url(self, url):
        """파이썬이 직접 URL에 접속하여 유효성을 확인합니다."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=7, allow_redirects=True)
            if response.status_code >= 200 and response.status_code < 300:
                return True, response.url
            return False, None
        except:
            return False, None

    def analyze_with_gemini_multimodal(self, video_path, context_info):
        video_file = None
        try:
            video_file = self.client.files.upload(file=video_path)
            while video_file.state.name == "PROCESSING":
                print(".", end="", flush=True)
                time.sleep(2)
                video_file = self.client.files.get(name=video_file.name)

            prompt = f"""
당신은 광고 유입 경로를 추적하는 마케팅 데이터 전문가입니다.
제공된 [영상 파일]과 [메타 데이터]를 분석하여, 이 광고가 최종적으로 소비자를 도달시키려는 '최정점의 구매 페이지'를 결정하세요.

[광고 메타 데이터]
{context_info}

[분석 지침]
1. 의도 파악: 브랜드명과 제품명을 정확히 식별하세요.
2. 후보지 탐색: 구글 검색을 활용하여 자사몰 상세페이지, 네이버 스마트스토어, 쿠팡 등 '모든 가능한 구매 경로'를 후보 리스트에 담으세요.
3. 우선순위: 독립 자사몰(.co.kr, .com)의 상세 페이지를 리스트 최상단에 배치하세요.
4. 반드시 'landing_page_candidates'라는 키에 URL 리스트를 담아 JSON으로 응답하세요.

JSON 응답 형식:
{{
  "brand": "식별된 브랜드명",
  "product_name": "제품명",
  "landing_page_candidates": ["URL1", "URL2", "URL3"],
  "evidence": "근거 요약"
}}
"""
            # 안정적인 호출을 위해 검색 툴만 켜고, 파싱은 정규식으로 처리
            response = self.client.models.generate_content(
                model="gemini-2.5-flash", # 사용자 환경에 따라 gemini-1.5-flash로 변경 가능
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )

            # 정규식으로 JSON 추출
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if not json_match:
                raise ValueError(f"JSON 형식을 찾을 수 없음: {response.text}")
            
            res_data = json.loads(json_match.group())
            candidates = res_data.get('landing_page_candidates', [])

            print(f"\n🔍 {len(candidates)}개의 후보 링크 물리 검증 중...")
            
            final_url = "유효한 링크 없음"
            confidence = 0.0
            
            # 파이썬 물리 검증 루프
            for url in candidates:
                is_live, real_url = self.verify_url(url)
                if is_live:
                    print(f"✅ 유효 링크 발견: {real_url}")
                    final_url = real_url
                    confidence = 1.0 if any(x in real_url for x in ["/products/", "/goods/", "/shop/"]) else 0.7
                    break
            
            res_data['landing_page_url'] = final_url
            res_data['confidence'] = confidence
            return res_data

        except Exception as e:
            print(f"\n❌ 분석 에러: {e}")
            return {"brand": "실패", "landing_page_url": str(e)}
        finally:
            if video_file:
                try: self.client.files.delete(name=video_file.name)
                except: pass

    def analyze(self, url):
        v_id = self.extract_video_id(url)
        print(f"\n🎬 [분석 시작] ID: {v_id}")
        
        video_res = self.youtube.videos().list(part='snippet,statistics', id=v_id).execute()
        snippet = video_res['items'][0]['snippet']
        
        context_text = f"""
        - 채널 정보: {snippet['channelTitle']}
        - 영상 제목: {snippet['title']}
        - 영상 설명란 원문: {snippet['description']}
        - 영상 자막 스크립트: {self.get_transcript(v_id)}
        - 상위 댓글 내용: {self.get_comments(v_id)}
        """
        
        video_path = self.download_video(url)
        
        try:
            ai_result = self.analyze_with_gemini_multimodal(video_path, context_text)
            return {
                "brand": ai_result.get('brand', '알 수 없음'),
                "product_name": ai_result.get('product_name', '정보 없음'),
                "landing_page_url": ai_result.get('landing_page_url', '찾을 수 없음'),
                "confidence": ai_result.get('confidence', 0.0),
                "evidence": ai_result.get('evidence', '알 수 없음')
            }
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

# --- [추가] 2단계: 브랜드 신뢰도 및 상세 정보 정밀 검증 클래스 ---
class BrandTrustAnalyzer:
    def __init__(self, client):
        self.client = client
        self.model_id = "gemini-2.5-flash"

    def generate_trust_report(self, target_url: str, product_name: str, brand: str):
        print(f"\n🔎 2단계 정밀 리포트 생성 중: {target_url} 분석...")
        
        prompt = f"""
        당신은 기업 실사 및 제품 검증 전문가입니다. 
        제공된 URL({target_url})에 직접 접속하여, 먼저 이 페이지가 '브랜드/기업의 메인 사이트'인지 아니면 '특정 제품의 상세 판매 페이지'인지 판단한 후 아래 지침 중 하나를 선택하여 실행하십시오.

        ---
        ### 케이스 A: [브랜드/기업 메인 사이트]인 경우
        [조사 지침]
        1. 브랜드/기업 정체성: 이 사이트가 무엇을 하는 곳인지 페이지 내 텍스트를 바탕으로 정의하세요.
        2. 공식 근거(Claims) 수집: 사이트 내에 명시된 '특허 번호', '인증(KC, FDA 등)', '성분/기술 근거'를 찾아 리스트업하세요. 만약 내용이 없다면 반드시 "해당 정보 없음"이라고 명시하세요.
        3. 운영 주체 정보: 사이트 하단(Footer) 등에 기재된 법인명, 사업자 번호 등 공식 운영 주체 정보를 확인하세요.

        [출력 양식]
        - 브랜드/서비스 정체성
        - 공식 기술력 및 신뢰 근거
        - 운영 주체 정보
        - 조사 총평

        ---
        ### 케이스 B: [제품 상세 판매 페이지]
        **[타겟 제품명]: {product_name}**

        [조사 지침]
        1. 타겟 제품 매칭(Product Matching): 
           - 현재 페이지가 우리가 찾는 **'[{product_name}]'**에 대한 정보를 담고 있는지 가장 먼저 확인하십시오.
           - 만약 페이지에 여러 옵션이나 다른 제품이 섞여 있다면, 반드시 **'[{product_name}]'**과 관련된 정보만 선별하여 가져와야 합니다.

        2. 화면 내 데이터 전수 조사 (스크롤 필수):
           - [{product_name}]의 신뢰도를 입증하는 객관적 데이터만 현재 화면에서 추출하십시오.
           - 원산지(산지), 생산자/제조원 정보
           - 인증 증거: HACCP, GAP, 무농약, 혹은 전자제품 인증 번호 등
           - 품질 증거: 당도(Brix), 성분 분석표, 실제 촬영된 시험 성적서 이미지 내 텍스트 등

        3. 엄격한 데이터 격리: 
           - 외부 정보나 사전 지식을 배제하고, 현재 화면에 [{product_name}]에 대한 명시적인 근거가 없다면 "현재 페이지 내 근거 확인 불가"라고 보고하십시오.

        [출력 양식]
        - 입력된 타겟 제품명: {product_name}
        - 실제 식별된 제품 본질(Subject): 
        - 제조 및 생산 주체: 
        - 상세페이지 내 신뢰 근거 리스트: 
        - 데이터 정합성 확인: [타겟 제품 정보와 일치함 / 타겟과 다른 제품임 / 환각 주의]
        """

        try:
            # 2단계에서는 JSON이 아닌 텍스트 리포트이므로 단순 호출
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[{"google_search": {}}])
            )
            return response.text
        except Exception as e:
            return f"❌ 상세 검증 리포트 생성 중 에러 발생: {e}"

# --- [수정] 통합 실행 로직 ---
if __name__ == "__main__":
    tracer = LinkTracer()
    
    print("="*60)
    video_url = input("▶ 분석할 유튜브 링크를 입력하세요: ").strip()
    print("="*60)

    if video_url:
        # Step 1: 영상 분석 및 물리적 URL 검증
        result = tracer.analyze(video_url)
        print("\n" + "-"*20 + " [1단계: 영상 분석 및 URL 검증 결과] " + "-"*20)
        print(json.dumps(result, ensure_ascii=False, indent=4))
        
        # Step 2: 물리적으로 검증된 URL이 있다면 상세 리포트 생성
        final_link = result.get('landing_page_url')
        
        if final_link and "http" in final_link:
            # LinkTracer에 이미 생성된 client를 재사용
            trust_analyzer = BrandTrustAnalyzer(tracer.client)
            
            report = trust_analyzer.generate_trust_report(
                target_url=final_link,
                product_name=result.get('product_name'),
                brand=result.get('brand')
            )
            
            print("\n" + "="*20 + " [2단계: 브랜드 신뢰도 검증 리포트] " + "="*20)
            print(report)
        else:
            print("\n⚠️ 유효한 접속 가능 URL이 없어 2단계 리포트 생성을 스킵합니다.")