import os
import yt_dlp
import re
import json
import time
import requests
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google import genai  
from google.genai import types 
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

load_dotenv()

class LinkTracer:
    def __init__(self):
        self.gemini_key = os.getenv('API_KEY')
        self.youtube_api_key = os.getenv('Youtube_API_Key') or os.getenv('YT_SHORTS_API_KEY')
        
        if not self.gemini_key:
            raise ValueError("❌ api_key_grounding가 설정되어 있지 않습니다!")

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

    def download_video(self, video_url):
        # 파일명이 겹치지 않게 timestamp 사용
        temp_filename = f"temp_{int(time.time() * 1000)}.mp4"
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
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=7, allow_redirects=True)
            if 200 <= response.status_code < 300:
                return True, response.url
            return False, None
        except:
            return False, None

    def analyze_with_gemini_multimodal(self, video_path, context_info):
        video_file = None
        try:
            # Gemini 파일 업로드
            video_file = self.client.files.upload(file=video_path)
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = self.client.files.get(name=video_file.name)

            prompt = f"""
            당신은 광고 유입 경로를 추적하는 마케팅 데이터 전문가입니다.
            제공된 [영상 파일]과 [메타 데이터]를 분석하여, 이 광고가 최종적으로 소비자를 도달시키려는 '최정점의 구매 페이지'를 결정하세요.

            [광고 메타 데이터]
            {context_info}

            [분석 지침]
            1. 의도 파악: 브랜드명과 제품명을 정확히 식별하세요.
            2. 후보지 탐색: 구글 검색을 활용하여 자사몰 상세페이지, 자사몰 공식페이지, 네이버 스마트스토어, 쿠팡 등 '모든 가능한 구매 경로'를 후보 리스트에 담으세요.
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
            response = self.client.models.generate_content(
                model="gemini-2.5-flash", # 최신 모델명 확인 필요
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(tools=[{"google_search": {}}])
            )

            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if not json_match: raise ValueError("AI 응답에서 JSON 추출 실패")
            
            res_data = json.loads(json_match.group())
            if json_match:
                res_data = json.loads(json_match.group())
            else:
        # 에러 발생 시 로그를 찍어주면 디버깅이 편합니다.
                print(f"AI RAW RESPONSE: {response.text}") 
                raise ValueError("AI 응답에서 JSON 구조를 찾을 수 없습니다.")

            candidates = res_data.get('landing_page_candidates', [])

            final_url = "유효한 링크 없음"
            for url in candidates:
                is_live, real_url = self.verify_url(url)
                if is_live:
                    final_url = real_url
                    break
            
            res_data['landing_page_url'] = final_url
            return res_data
        finally:
            if video_file: 
                self.client.files.delete(name=video_file.name)

    def analyze(self, url):
        v_id = self.extract_video_id(url)
        video_res = self.youtube.videos().list(part='snippet', id=v_id).execute()
        
        if not video_res['items']:
            raise ValueError("유튜브 API에서 영상 정보를 가져올 수 없습니다.")
            
        snippet = video_res['items'][0]['snippet']
        context_text = f"제목: {snippet['title']} | 설명: {snippet['description']} | 자막: {self.get_transcript(v_id)}"
        
        # 영상 다운로드
        video_path = self.download_video(url)
        
        try:
            return self.analyze_with_gemini_multimodal(video_path, context_text)
        finally:
            # 분석 후 로컬 영상 파일 즉시 삭제
            if os.path.exists(video_path): 
                os.remove(video_path)


class BrandTrustAnalyzer:
    def __init__(self, client):
        self.client = client
        self.model_id = "gemini-2.5-flash"

    def generate_trust_report(self, target_url: str, product_name: str, brand: str):
        prompt = f"""
        당신은 기업 실사 및 제품 검증 전문가입니다. 제공된 URL({target_url})에 직접 접속하여, 먼저 이 페이지가 '브랜드/기업의 메인 사이트'인지 아니면 '특정 제품의 상세 판매 페이지'인지 판단한 후 아래 지침에 따라 분석 후, [출력 JSON 구조 가이드]에 맞게 내용 정리해서 JSON으로 응답하십시오.

        ### 케이스 A: [브랜드/기업 메인 사이트]인 경우

        [조사 지침]
        1. 브랜드/기업 정체성: 이 사이트가 무엇을 하는 곳인지 페이지 내 텍스트를 바탕으로 정의하세요.
        2. 공식 근거(Claims) 수집: 사이트 내에 명시된 '특허 번호', '인증(KC, FDA 등)', '성분/기술 근거'를 찾아 리스트업하세요. 추측은 절대 금지하며, 내용이 없다면 반드시 "해당 정보 없음"이라고 명시하세요.
        3. 운영 주체 정보: 사이트 하단(Footer) 등에 기재된 법인명, 사업자 번호 등 공식 운영 주체 정보를 확인하세요.

        ### 케이스 B: [제품 상세 판매 페이지]인 경우
        [타겟 제품명]: {product_name}

        [조사 지침]
        1. 타겟 제품 매칭(Product Matching):
        -현재 페이지가 우리가 찾는 '[{product_name}]'에 대한 정보를 담고 있는지 최우선으로 확인하십시오.
        -여러 옵션이 섞여 있다면, 반드시 '[{product_name}]'과 직접 관련된 정보만 선별하십시오.

        2. 화면 내 데이터 전수 조사 (스크롤 및 텍스트 추출):
        -원산지/제조원: 실제 생산지 및 제조사 정보를 명시하십시오.
        -인증/품질 증거: HACCP, KC인증번호, 당도(Brix), 성분 분석표 등 화면에 '텍스트'나 '이미지 내 글자'로 존재하는 데이터만 추출하십시오.
        -구매자 리뷰 분석: 실제 구매평 섹션을 분석하여 (1) 주요 긍정 피드백과 (2) 반복되는 불만 사항을 요약하십시오. 리뷰가 없다면 "등록된 리뷰 없음"으로 기재하십시오.

        3.환각 방지 및 데이터 격리 (Strict Rule):
        -외부 지식 차단: 당신이 기존에 알고 있던 상식이나 외부 정보를 완전히 배제하고, 오직 현재 페이지에 노출된 데이터만 사용하십시오.
        -추론 금지: "있을 것으로 보임", "우수할 것으로 추정됨"과 같은 추측성 단어 사용 시 오답으로 간주합니다. 정보가 없으면 "페이지 내 근거 확인 불가"라고 단호하게 답변하십시오.

        [출력 JSON 구조 가이드]
        {{
            "analysis_case": "CASE_A 또는 CASE_B",
            "detected_subject": "식별된 대상 이름",
            "site_details": {{
                # CASE_A일 때만 사용 (그 외 null)
                "brand_identity": "내용",
                "official_claims": {{"patents": [], "certifications": [], "tech_evidence": ""}},
                "business_entity": {{"company_name": "", "business_number": "", "address": ""}},
                
                # CASE_B일 때만 사용 (그 외 null)
                "product_verification": {{
                    "is_target_matched": true/false,
                    "manufacturer_info": "원산지 및 제조원",
                    "trust_indicators": ["인증리스트"],
                    "review_analysis": {{"positive": [], "negative": []}}
                }}
            }}
        }}
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[{"google_search": {}}])
            )
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                print(f"AI RAW RESPONSE (Trust): {response.text}")
                return {"error": "AI 응답에서 JSON 구조를 찾을 수 없습니다."}
            
        except Exception as e:
            return {"error": str(e)}