from google import genai
from google.genai import types
import time
import json
import os
from dotenv import load_dotenv

load_dotenv()

# 1. 클라이언트 설정
client = genai.Client(api_key=os.getenv("API_KEY"))

# 2. 분석할 동영상 경로 (본인의 경로로 수정)
VIDEO_PATH = r"C:\\Users\\LG\\OneDrive\\Desktop\\ai 영상\\E.mp4"

def analyze_with_gemini_25(video_path: str) -> tuple[float, float] | None:
    try:
        # [STEP 1] 동영상 파일 업로드
        print("📤 Gemini 2.5 서버로 동영상 업로드 중...")
        video_file = client.files.upload(file=video_path)
        print(f"✅ 업로드 완료: {video_file.name}")

        # [STEP 2] 동영상 처리 대기
        while video_file.state.name == "PROCESSING":
            print("⏳ Gemini 2.5가 동영상을 분석 준비 중입니다...", end="\r")
            time.sleep(2)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            print("\n❌ 동영상 처리 실패")
            return 0, 0

        print("\n🚀 Gemini 2.5 Flash 분석 시작!")

        prompt = """
        Analyze this video carefully to see if it was created by AI.
        Provide your final judgment ONLY in the following JSON format. 
        No other text or explanation.
        
        {
          "ai_score": (0 to 100 integer),
          "human_score": (0 to 100 integer)
        }
        """

        # [STEP 3] 분석 요청 (models/gemini-2.5-flash 사용)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=video_file.uri,
                            mime_type=video_file.mime_type),
                        types.Part.from_text(text=prompt),
                    ]),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        # [STEP 4] 결과 데이터 추출
        # response_mime_type="application/json" 설정을 했으므로 바로 파싱 가능하거나 text로 받음 
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(res_text)

        ai_val = data.get('ai_score', 0.0)
        human_val = data.get('human_score', 0.0)

        print(f"✅ 분석 성공! AI 확률: {ai_val}% / 실제 촬영 확률: {human_val}%")
        
        # (선택 사항) 업로드한 파일 삭제
        client.files.delete(name=video_file.name)

        return ai_val, human_val

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    analyze_with_gemini_25(VIDEO_PATH)