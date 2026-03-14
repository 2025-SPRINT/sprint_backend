import pandas as pd
import json
import asyncio
import time
import os
from datetime import datetime

# 기존 라이브러리 임포트 (경로가 올바른지 확인하세요)
from app import get_youtube_transcript2, run_site_verification
from gemini_main import analyze_ad

# ==========================================
# 1. 설정 및 경로
# ==========================================
INPUT_FILE = "스프린트 데이터셋.csv"  # 이미지의 CSV 파일명
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTPUT_FILE = f"batch_analysis_result_{TIMESTAMP}.csv"

async def process_video(video_url, row_data):
    """
    비동기로 유튜브 분석 및 신규 Gemini 파이프라인(analyze_ad) 평가 수행
    """
    try:
        # 1. 자막 및 사이트 정보 병렬 추출
        print(f"   - 데이터 추출 중: {video_url}")
        task_transcript = asyncio.to_thread(get_youtube_transcript2, video_url)
        task_site_trace = asyncio.to_thread(run_site_verification, video_url)
        
        script_text, trust_report = await asyncio.gather(task_transcript, task_site_trace)

        if not script_text:
            script_text = "자막 없음. 제공된 브랜드/사이트 정보를 바탕으로 분석하세요."

        # 2. trust_report에서 gemini_main.analyze_ad에 필요한 데이터 추출
        # trust_report의 구조가 {'site_analysis': ..., 'discovery': ..., 'comments': ...} 형태라고 가정
        site_details = trust_report.get('site_analysis', {}) if isinstance(trust_report, dict) else None
        discovery_data = trust_report.get('discovery', {}) if isinstance(trust_report, dict) else None
        
        # CSV에 별도 댓글 컬럼이 있으면 우선 사용, 없으면 trust_report에서 가져옴
        comments_data = row_data.get('comment', '') 
        if not comments_data and isinstance(trust_report, dict):
            comments_data = trust_report.get('comments', '')

        # 3. 신규 Gemini 통합 분석 실행 (Step 1: Fact, Step 2: Patent, Step 3: Synthesis)
        print(f"   - Gemini 심층 분석 시작 (Google Search & KIPRIS 활용)...")
        report_json_str = await analyze_ad(
            script_text=script_text,
            site_details=site_details,
            comments_data=comments_data,
            discovery_data=discovery_data
        )
        
        # 결과 JSON 파싱
        analysis_result = json.loads(report_json_str)
        return script_text, trust_report, analysis_result

    except Exception as e:
        print(f"   ⚠️ 오류 발생: {str(e)}")
        return None, None, {
            "reliability_level": "분석실패", 
            "risk_score": "0", 
            "error": str(e),
            "summary": "분석 중 예외가 발생했습니다."
        }

# ==========================================
# 2. 메인 실행부
# ==========================================
def run_csv_batch():
    print(f"📂 CSV 데이터 로드 중: {INPUT_FILE}")
    
    # 인코딩: 이미지에서 깨짐 현상이 보였으므로 utf-8-sig 권장
    try:
        df = pd.read_csv(INPUT_FILE, encoding='utf-8-sig')
    except Exception as e:
        print(f"❌ 파일을 읽을 수 없습니다: {e}")
        return

    results = []

    # 전체 행 반복
    for index, row in df.iterrows():
        v_id = str(row['video_id']).strip()
        
        if not v_id or v_id in ['nan', '#NAME?', 'None', '']:
            print(f"⏩ [{index+1}] 유효하지 않은 video_id 건너뜀")
            continue
        
        video_url = f"https://www.youtube.com/shorts/{v_id}"
        print(f"\n🚀 [{index+1}/{len(df)}] 분석 프로세스 가동: {v_id}")
        
        # 신규 파이프라인 비동기 실행
        try:
            script, site_info, analysis = asyncio.run(process_video(video_url, row))
        except Exception as e:
            print(f"   ❌ 비동기 루프 실행 오류: {e}")
            continue
        
        # 결과 필드 매핑 (CSV 저장용)
        result_item = {
            "순서": index + 1,
            "video_id": v_id,
            "channel_name": row.get('channel_name', 'N/A'),
            "human_score(정답)": row.get('human_score', 'N/A'),
            "AI등급": analysis.get('reliability_level', '실패'),
            "리스크점수": analysis.get('risk_score', '0'),
            "핵심요약": analysis.get('summary', '분석 불가'),
            "위반사항_상세": json.dumps(analysis.get('score_breakdown', []), ensure_ascii=False),
            "특허검증결과": json.dumps(analysis.get('patent_check', {}), ensure_ascii=False),
            "증거_팩트체크": json.dumps(analysis.get('evidence', []), ensure_ascii=False),
            "전문_로그": json.dumps(analysis, ensure_ascii=False)
        }
        
        results.append(result_item)
        print(f"✅ 결과 저장 완료: {result_item['AI등급']} (Score: {result_item['리스크점수']})")
        
        # API 할당량 및 안정성을 위한 딜레이 (필요시 조절)
        time.sleep(2)

    # 최종 결과를 CSV로 저장
    output_df = pd.DataFrame(results)
    output_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    print(f"\n✨ 모든 작업이 완료되었습니다!")
    print(f"   💾 결과 파일명: {OUTPUT_FILE}")

if __name__ == "__main__":
    run_csv_batch()