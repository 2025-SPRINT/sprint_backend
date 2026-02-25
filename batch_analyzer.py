import requests
import json
import pandas as pd
import os
import time
from datetime import datetime

# ==========================================
# 1. 설정 및 분석 대상 URL 리스트
# ==========================================
BASE_URL = "http://localhost:5173/api/video/analyze" # app.py 서버 주소
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTPUT_DIR = f"analysis_report_{TIMESTAMP}"

# 분석할 쇼츠 URL들을 이 리스트에 넣으세요
video_urls = [
        "https://www.youtube.com/shorts/nMOaPYFPr2g"
]

# 결과 저장을 위한 폴더 생성
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(f"{OUTPUT_DIR}/raw_data", exist_ok=True)

def run_automation():
    summary_results = []
    
    print(f"🚀 [Batch Start] 총 {len(video_urls)}개의 광고 분석을 시작합니다.")
    print(f"📂 모든 결과는 '{OUTPUT_DIR}' 폴더에 기록됩니다.\n")

    for i, url in enumerate(video_urls, 1):
        # URL에서 Video ID 추출 (간단하게)
        v_id = url.split('/')[-1].split('?')[0]
        print(f"[{i}/{len(video_urls)}] 분석 중: {v_id}...")
        
        try:
            # 1. app.py 서버에 통합 분석 요청 (5분 타임아웃)
            response = requests.post(BASE_URL, json={"url": url}, timeout=300)
            
            if response.status_code == 200:
                full_content = response.json().get('data', {})
                
                # [저장 1] 원본 데이터 전체를 JSON으로 백업
                with open(f"{OUTPUT_DIR}/raw_data/{v_id}.json", "w", encoding="utf-8") as f:
                    json.dump(full_content, f, ensure_ascii=False, indent=4)
                
                # 데이터 파싱 (Gemini 분석 결과 추출)
                analysis = full_content.get('analysis_result', {})
                trust_info = full_content.get('site_info', {}).get('step2_deep_verification', {})
                landing_url = full_content.get('site_info', {}).get('step1_video_discovery', {}).get('landing_page_url')

                # [저장 2] 가이드라인에 따른 엑셀용 데이터 구성
                summary_results.append({
                    "Video_ID": v_id,
                    "브랜드": analysis.get('brand'),
                    "제품명": analysis.get('product_name'),
                    "신뢰등급(reliability)": analysis.get('reliability_level'), # 가이드라인 1번
                    "신뢰점수(risk_score)": analysis.get('risk_score'),
                    "한줄요약(summary)": analysis.get('summary'),               # 가이드라인 2번
                    "문제점(issues)": ", ".join(analysis.get('issues', [])),   # 가이드라인 3번
                    "특허정보(patent)": analysis.get('patent_check'),           # 가이드라인 4번
                    "신뢰점수": trust_info.get('trust_score', 0),
                    "핵심조언(consultation)": analysis.get('consultation'),     # 가이드라인 6번
                    "근거(evidence)": analysis.get('evidence'),                 # 가이드라인 5번
                    "최종랜딩페이지": landing_url,
                    "원본URL": url
                })
                print(f"✅ 분석 완료: {analysis.get('brand')} (등급: {analysis.get('reliability_level')})")
            else:
                print(f"❌ 분석 실패: {v_id} (HTTP {response.status_code})")
                
        except Exception as e:
            print(f"⚠️ 에러 발생 ({v_id}): {str(e)}")
            
        # 서버 부하 방지를 위한 짧은 휴식
        time.sleep(1.5)

    # 2. 최종 엑셀 파일 생성
    if summary_results:
        df = pd.DataFrame(summary_results)
        excel_path = f"{OUTPUT_DIR}/total_summary_report.xlsx"
        df.to_excel(excel_path, index=False)
        print(f"\n✨ [Batch Finished] 모든 분석이 완료되었습니다!")
        print(f"📊 최종 보고서: {excel_path}")
    else:
        print("\n❌ 분석된 결과가 없어 보고서를 생성하지 못했습니다.")

if __name__ == "__main__":
    run_automation()