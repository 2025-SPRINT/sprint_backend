import google.generativeai as genai
import time
import json
import matplotlib.pyplot as plt
import os
from dotenv import load_dotenv
load_dotenv()

# 1. API 설정
genai.configure(api_key=os.getenv("API_KEY"))

# 2. 분석할 동영상 경로 (본인의 경로로 수정)
VIDEO_PATH = r"C:\\Users\\LG\\OneDrive\\Desktop\\ai 영상\\E.mp4"

def analyze_with_gemini_25():
    try:
        # [STEP 1] 동영상 파일 업로드
        print("📤 Gemini 2.5 서버로 동영상 업로드 중...")
        video_file = genai.upload_file(path=VIDEO_PATH)
        print(f"✅ 업로드 완료: {video_file.name}")

        # [STEP 2] 동영상 처리 대기
        while video_file.state.name == "PROCESSING":
            print("⏳ Gemini 2.5가 동영상을 분석 준비 중입니다...", end="\r")
            time.sleep(2)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            print("\n❌ 동영상 처리 실패")
            return

        print("\n🚀 Gemini 2.5 Flash 분석 시작!")

        # [STEP 3] 모델 설정 (models/gemini-2.5-flash 사용)
        model = genai.GenerativeModel(model_name="models/gemini-2.5-flash")
        
        prompt = """
        Analyze this video carefully to see if it was created by AI.
        Provide your final judgment ONLY in the following JSON format. 
        No other text or explanation.
        
        {
          "ai_score": (0 to 100 integer),
          "human_score": (0 to 100 integer)
        }
        """

        # 분석 요청
        response = model.generate_content([prompt, video_file])

        # [STEP 4] 결과 데이터 추출 (JSON 파싱)
        # Gemini가 가끔 앞뒤에 붙이는 ```json 문구 제거
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(res_text)

        ai_val = data.get('ai_score', 0)
        human_val = data.get('human_score', 0)

        # [STEP 5] 그래프 그리기
        labels = ['AI Generated', 'Human Created']
        scores = [ai_val, human_val]
        colors = ['#FF6B6B', '#4D96FF']

        plt.figure(figsize=(7, 7))
        plt.pie(scores, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors, explode=(0.05, 0))
        plt.title(f"Gemini 2.5 Analysis: {video_file.display_name}")
        plt.show()

        print(f"✅ 분석 성공! AI 확률: {ai_val}% / 실제 촬영 확률: {human_val}%")
        
        # (선택 사항) 업로드한 파일 삭제 - 서버를 깔끔하게 유지하려면 주석 해제
        # genai.delete_file(video_file.name)

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        print("💡 팁: JSON 파싱 에러가 난다면 Gemini의 응답이 형식을 지키지 않은 것일 수 있습니다.")

# 코드 실행
analyze_with_gemini_25()