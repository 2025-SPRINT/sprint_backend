import pandas as pd
import json
import asyncio
import time
from datetime import datetime

# 기존 라이브러리 임포트 (파일 경로 확인 필요)
from app import get_youtube_transcript2, run_site_verification
from gemini_main import evaluate_with_site_info

# ==========================================
# 1. 설정 및 경로
# ==========================================
# 엑셀 파일명으로 정확히 지정
INPUT_FILE = "스프린트 테스트결과.xlsx" 
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTPUT_FILE = f"batch_retest_{TIMESTAMP}.xlsx"

async def process_video(video_url):
    """비동기로 유튜브 분석 및 Gemini 평가 수행"""
    try:
        # 1. 자막 및 사이트 정보 병렬 추출
        task_transcript = asyncio.to_thread(get_youtube_transcript2, video_url)
        task_site_trace = asyncio.to_thread(run_site_verification, video_url)
        script_text, trust_report = await asyncio.gather(task_transcript, task_site_trace)

        if not script_text:
            script_text = "자막 없음. 제공된 브랜드/사이트 정보를 바탕으로 분석하세요."

        # 2. Gemini 통합 분석
        report = await evaluate_with_site_info(script_text, trust_report)
        
        # 결과 JSON 파싱 및 정제
        if isinstance(report, str):
            clean_report = report.replace("```json", "").replace("```", "").strip()
            analysis_result = json.loads(clean_report)
        else:
            analysis_result = report
            
        return script_text, trust_report, analysis_result
    except Exception as e:
        return None, None, {"error": str(e)}

# ==========================================
# 2. 메인 실행부
# ==========================================
def run_excel_batch():
    print(f"📂 엑셀 데이터 로드 중: {INPUT_FILE}")
    
    # pandas의 read_excel을 사용하여 직접 읽기
    # 엔진은 보통 'openpyxl'을 사용합니다.
    try:
        df = pd.read_excel(INPUT_FILE)
    except Exception as e:
        print(f"❌ 엑셀 파일을 읽을 수 없습니다: {e}")
        return

    results = []

    for index, row in df.iterrows():
        # 엑셀의 'Video_ID' 컬럼 읽기
        v_id = str(row['Video_ID']).strip()
        
        # 엑셀 특유의 오류값이나 빈 셀 처리
        if not v_id or v_id in ['nan', '#NAME?', 'None']:
            print(f"⏩ [{index+1}] 유효하지 않은 ID 건너뜀")
            continue
        
        video_url = f"https://www.youtube.com/shorts/{v_id}"
        print(f"\n🚀 [{index+1}/{len(df)}] 분석 시작: {v_id}")
        
        # 비동기 분석 실행
        script, site_info, analysis = asyncio.run(process_video(video_url))
        
        # 결과 매핑 (기존 정답 보존)
        result_item = {
            "순서": row.get('순서', index + 1),
            "Video_ID": v_id,
            "원본_위험도(정답)": row.get('원본_위험도(정답)', 'N/A'),
            "기존_AI등급": row.get('신뢰등급(AI)', 'N/A'),
            "신규_AI등급": analysis.get('reliability_level', '실패'),
            "신규_리스크점수": analysis.get('risk_score', 0),
            "요약": analysis.get('summary', '분석 실패'),
            "증거": json.dumps(analysis.get('evidence', []), ensure_ascii=False),
            "로그_JSON": json.dumps(analysis, ensure_ascii=False)
        }
        
        results.append(result_item)
        print(f"✅ 결과: {result_item['신규_AI등급']} (점수: {result_item['신규_리스크점수']})")
        
        # API 안정성을 위한 간격
        time.sleep(1)

    # 최종 결과를 다시 엑셀로 저장
    output_df = pd.DataFrame(results)
    output_df.to_excel(OUTPUT_FILE, index=False)
    print(f"\n✨ 모든 작업 완료! 결과물: {OUTPUT_FILE}")

if __name__ == "__main__":
    run_excel_batch()