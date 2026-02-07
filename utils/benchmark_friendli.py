"""
Friendli.ai 모델 성능 비교 벤치마크
- 모델: K-EXAONE, Qwen, DeepSeek
- 평가 지표: F1 Score, Precision, Recall, Accuracy
"""

import asyncio
import csv
import json
import time
from collections import defaultdict
from friendli_main import main as friendli_analyze

# 테스트할 모델 목록
MODELS = {
    "K-EXAONE": "LGAI-EXAONE/K-EXAONE-236B-A23B",
    "Qwen3": "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "DeepSeek-V3.1": "deepseek-ai/DeepSeek-V3.1",
}

# reliability_level을 이진 분류로 변환
# "위험" = 허위광고(1), 나머지 = 정상(0)
def reliability_to_binary(level: str) -> int:
    level = level.strip() if level else ""
    if level in ["위험"]:
        return 1
    return 0


def calculate_metrics(y_true: list, y_pred: list) -> dict:
    """Precision, Recall, F1, Accuracy 계산"""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(y_true) if len(y_true) > 0 else 0.0
    
    return {
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "Precision": round(precision, 4),
        "Recall": round(recall, 4),
        "F1": round(f1, 4),
        "Accuracy": round(accuracy, 4),
    }


async def run_benchmark():
    # 1. CSV 로드
    scripts = []
    with open("scripts.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scripts.append({
                "ad": row["ad"],
                "isHoax": int(row["isHoax"]),
                "script": row["script"],
            })
    
    print(f"📊 총 {len(scripts)}개 광고 스크립트 로드 완료\n")
    print("=" * 80)
    
    # 2. 모델별 결과 저장
    results = defaultdict(list)  # model_name -> [(gt, pred, level, time), ...]
    detailed_reports = defaultdict(list)  # model_name -> [report_json, ...]
    
    # 3. 각 모델에 대해 벤치마크 실행
    for model_label, model_id in MODELS.items():
        print(f"\n🚀 [{model_label}] 벤치마크 시작...")
        print("-" * 60)
        
        for i, item in enumerate(scripts, 1):
            ad_name = item["ad"]
            gt = item["isHoax"]
            script = item["script"]
            
            start = time.perf_counter()
            try:
                report_json = await friendli_analyze("", script, model_name=model_id)
                elapsed = time.perf_counter() - start
                
                # JSON 파싱
                try:
                    report = json.loads(report_json)
                    level = report.get("reliability_level", "정보 부족")
                    pred = reliability_to_binary(level)
                except json.JSONDecodeError:
                    level = "파싱 에러"
                    pred = 0
                    report = {"error": "JSON 파싱 실패"}
                
                # 결과 기록
                results[model_label].append((gt, pred, level, elapsed))
                detailed_reports[model_label].append({
                    "ad": ad_name,
                    "gt": "허위" if gt == 1 else "정상",
                    "pred": "허위" if pred == 1 else "정상",
                    "level": level,
                    "time": round(elapsed, 2),
                    "correct": "✓" if gt == pred else "✗",
                    "report": report,
                })
                
                status = "✓" if gt == pred else "✗"
                print(f"  [{i:2d}/11] {ad_name[:12]:12s} | GT: {'허위' if gt else '정상'} | 예측: {level:6s} | {status} | {elapsed:.2f}s")
                
            except Exception as e:
                elapsed = time.perf_counter() - start
                print(f"  [{i:2d}/11] {ad_name[:12]:12s} | 에러: {str(e)[:30]}...")
                results[model_label].append((gt, 0, "에러", elapsed))
                detailed_reports[model_label].append({
                    "ad": ad_name,
                    "gt": "허위" if gt == 1 else "정상",
                    "pred": "에러",
                    "level": "에러",
                    "time": round(elapsed, 2),
                    "correct": "✗",
                    "report": {"error": str(e)},
                })
    
    # 4. 결과 요약
    print("\n" + "=" * 80)
    print("📈 성능 비교 결과\n")
    
    summary = []
    for model_label in MODELS.keys():
        model_results = results[model_label]
        y_true = [r[0] for r in model_results]
        y_pred = [r[1] for r in model_results]
        times = [r[3] for r in model_results]
        
        metrics = calculate_metrics(y_true, y_pred)
        avg_time = sum(times) / len(times) if times else 0
        
        summary.append({
            "Model": model_label,
            **metrics,
            "Avg Time (s)": round(avg_time, 2),
        })
        
        print(f"🔹 {model_label}")
        print(f"   Accuracy: {metrics['Accuracy']:.2%}  |  Precision: {metrics['Precision']:.2%}  |  Recall: {metrics['Recall']:.2%}  |  F1: {metrics['F1']:.2%}")
        print(f"   TP: {metrics['TP']}  FP: {metrics['FP']}  TN: {metrics['TN']}  FN: {metrics['FN']}  |  Avg Time: {avg_time:.2f}s")
        print()
    
    # 5. 상세 결과를 JSON으로 저장
    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "summary": summary,
            "detailed": detailed_reports,
        }, f, ensure_ascii=False, indent=2)
    
    print("=" * 80)
    print("✅ 벤치마크 완료! 상세 결과: benchmark_results.json")
    
    return summary, detailed_reports


if __name__ == "__main__":
    asyncio.run(run_benchmark())
