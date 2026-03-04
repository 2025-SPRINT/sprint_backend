#썸네일 o 버전

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
                order="relevance" # 관련성 높은 댓글 우선
            )
            response = request.execute()
            comments = [item['snippet']['topLevelComment']['snippet']['textDisplay'] for item in response.get('items', [])]
            return " | ".join(comments) if comments else "댓글 없음"
        except Exception as e:
            print(f"⚠️ [Comment Error] {e}")
            return "댓글 기능을 사용할 수 없거나 댓글이 없습니다."

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
                # 바이너리 데이터를 반환하거나 임시 파일로 저장
                return response.content
            return None
        except Exception as e:
            print(f"⚠️ [Image Download Error] {e}")
            return None

    def get_transcript(self, video_id):
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            return TextFormatter().format_transcript(transcript).replace('\n', ' ').strip()
        except: return "자막 없음"

    def verify_url(self, url):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=7, allow_redirects=True)
            if 200 <= response.status_code < 300:
                return True, response.url
            return False, None
        except:
            return False, None

    def analyze_with_gemini_text(self, context_info, image_bytes=None, retry_count=0):
        MAX_RETRIES = 3
        prompt = f"""

        당신은 광고 유입 경로를 추적하는 마케팅 데이터 전문가입니다.
제공된 **[메타 데이터]**와 **[썸네일 이미지]**를 심층 분석하여, 소비자가 최종 도달하게 될 '최정점의 구매 페이지'를 결정하세요.

[데이터 정보]
메타 데이터: {context_info}
썸네일 이미지: (사용자가 업로드한 이미지 파일)

[분석 지침]
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
 
JSON 응답 형식:
 {{
 "brand": "식별된 브랜드명",
 "Corporate Name": "법인명",
 "product_name": "상품명",
 "landing_page_candidates": ["URL1", "URL2", "URL3"],
"evidence": "검색 결과의 어떤 정보를 바탕으로 결정했는지 상세 기술"
}}

            """
        
        contents = [prompt]
        if image_bytes:
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash", # 모델명 오타 확인 (2.5 -> 2.0 등 환경에 맞게)
                contents=contents,
                config=types.GenerateContentConfig(tools=[{"google_search": {}}])
            )

            raw_text = response.text.strip()
            
            # JSON 추출 로직
            json_pattern = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)
            match = json_pattern.search(raw_text)
            
            if match:
                json_str = match.group(1)
            else:
                fallback_pattern = re.compile(r'(\{.*\})', re.DOTALL)
                fallback_match = fallback_pattern.search(raw_text)
                json_str = fallback_match.group(1) if fallback_match else raw_text

            res_data = json.loads(json_str, strict=False)
            
        except Exception as e:
            print(f"❌ [Gemini API Error] {e}")
            res_data = {"landing_page_candidates": [], "brand": "분석 실패", "evidence": str(e)}

        # URL 검증 부분
        candidates = res_data.get('landing_page_candidates', [])
        final_url = "유효한 링크 없음"
        
        for url in candidates:
            is_live, real_url = self.verify_url(url)
            if is_live:
                final_url = real_url
                break

        # 재시도 로직 (메서드 이름 변경에 맞춰 수정)
        if final_url == "유효한 링크 없음" and retry_count < MAX_RETRIES:
            retry_count += 1
            print(f"⚠️ [Retry {retry_count}/{MAX_RETRIES}] 유효한 링크가 발견되지 않아 재시도합니다...")
            # 재시도 시 약간의 대기 시간을 주어 API 할당량 문제를 방지할 수 있습니다.
            time.sleep(1) 
            return self.analyze_with_gemini_text(context_info, image_bytes, retry_count=retry_count)
        
        res_data['landing_page_url'] = final_url
        return res_data

    def analyze(self, url, hint_data=None):
        v_id = self.extract_video_id(url)
        thumbnail_url = None
        
        # 1. 메타데이터 결정 (DB 혹은 API)
        if hint_data and hint_data.get('title') and hint_data.get('channel_name'):
            print(f"📦 [Cache Hit] DB 메타데이터 사용: {v_id}")
            channel_name = hint_data.get('channel_name')
            title = hint_data.get('title')
            description = hint_data.get('description', '설명 없음')
            thumbnail_url = hint_data.get('thumbnail_url') # DB에서 URL 가져옴
        else:
            print(f"🌐 [API Call] 유튜브 API 호출: {v_id}")
            video_res = self.youtube.videos().list(part='snippet', id=v_id).execute()
            if not video_res['items']:
                raise ValueError("영상을 찾을 수 없습니다.")
            snippet = video_res['items'][0]['snippet']
            channel_name = snippet.get('channelTitle')
            title = snippet.get('title')
            description = snippet.get('description')
            thumbnails = snippet.get('thumbnails', {})
            thumbnail_url = (thumbnails.get('maxres') or 
                             thumbnails.get('high') or 
                             thumbnails.get('default', {})).get('url')

        # 2. 이미지 다운로드 (DB에서 가져왔든 API에서 가져왔든 '분석'을 위해 다운로드 실행)
        # Gemini에게 '이미지' 자체를 전달해야 하므로 바이트화가 필요합니다.
        image_bytes = self.download_image(thumbnail_url) if thumbnail_url else None

        # 3. 동적 데이터(자막, 댓글) 수집
        transcript = self.get_transcript(v_id)
        comments = self.get_comments(v_id)

        context_text = f"""
        채널명: {channel_name}
        영상제목: {title}
        영상설명: {description}
        영상자막: {transcript}
        주요댓글: {comments}
        """
        
        # 4. 멀티모달 분석 수행 (텍스트 + 이미지 바이트)
        return self.analyze_with_gemini_text(context_text, image_bytes)

class BrandTrustAnalyzer:
    def __init__(self, client):
        self.client = client
        self.model_id = "gemini-2.5-flash" 

    def generate_trust_report(self, target_url: str, product_name: str, brand: str, max_retries=5):
        """
        최대 max_retries번 재시도하며 사이트 분석을 수행합니다.
        """
        last_error = ""
        
        for attempt in range(max_retries):
            try:
                print(f"🔄 [Attempt {attempt + 1}/{max_retries}] 분석 시작: {target_url}")
                
                # 시도 횟수에 따라 프롬프트에 약간의 강조를 추가 (강박적 검색 유도)
                extra_instruction = ""
                if attempt > 0:
                    extra_instruction = "\n⚠️ 이전 시도에서 정보를 찾지 못했습니다. 이번에는 더 깊게 검색하고 페이지의 푸터(Footer)까지 샅샅이 확인하세요."

                prompt = f"""
                당신은 기업 실사 및 제품 검증 전문가입니다. 제공된 URL({target_url})에 직접 접속하여, 먼저 이 페이지가 '브랜드/기업의 메인 사이트'인지 아니면 '특정 제품의 상세 판매 페이지'인지 판단한 후 아래 지침에 따라 분석 후, [출력 JSON 구조 가이드]에 맞게 내용을 정리해서 JSON으로 응답하십시오.

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

                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[{"google_search": {}}],
                        # 안전 설정을 낮춰서 차단 가능성을 줄임
                        safety_settings=[
                            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                        ]
                    )
                )

                if not response or not response.text:
                    raise ValueError("AI 응답이 비어있습니다 (Empty Response).")

                # JSON 추출
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    print(f"✅ [Success] {attempt + 1}번째 시도에서 분석 성공!")
                    return result
                else:
                    raise ValueError("JSON 구조를 찾을 수 없습니다.")

            except Exception as e:
                last_error = str(e)
                print(f"⚠️ [Attempt {attempt + 1}] 실패: {last_error}")
                # 재시도 전 잠깐 대기 (네트워크/서버 부하 고려)
                if attempt < max_retries - 1:
                    time.sleep(2) 

        # 모든 재시도가 실패했을 경우
        return {
            "error": "최대 재시도 횟수 초과",
            "last_error": last_error,
            "target_url": target_url
        }