import google.generativeai as genai

# 본인의 키를 넣어주세요
genai.configure(api_key="AIzaSyD7NQnSDuycZNDhy1AYOOxbd7Dhovjids8")

print("--- 사용 가능한 모델 목록 ---")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)

import google.generativeai as genai
import json
import matplotlib.pyplot as plt
import PIL.Image

# 1. 설정
genai.configure(api_key="AIzaSyD7NQnSDuycZNDhy1AYOOxbd7Dhovjids8")
model_name = 'models/gemini-2.5-flash' # 1단계에서 확인한 이름으로 수정 가능

try:
    # 2. 이미지 로드 (전체 경로 사용 추천)
    img_path = r"C:\Users\LG\OneDrive\Desktop\ai 영상\ai 이미지 1.png" 
    img = PIL.Image.open(img_path)

    # 3. 분석 요청
    model = genai.GenerativeModel(model_name)
    prompt = "이미지 분석 후 JSON으로만 답해: {'ai_score': 85, 'human_score': 15}"
    
    response = model.generate_content([prompt, img])
    
    # 4. 결과 파싱 및 그래프
    # JSON 텍스트 정제
    res_text = response.text.replace('```json', '').replace('```', '').strip()
    data = json.loads(res_text)
    
    # 그래프 출력
    plt.bar(['AI', 'Human'], [data['ai_score'], data['human_score']], color=['red', 'blue'])
    plt.title("Analysis Result")
    plt.show()
    
    print("성공적으로 그래프를 그렸습니다!")

except Exception as e:
    print(f"❌ 에러 발생: {e}")