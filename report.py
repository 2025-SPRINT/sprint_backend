import pandas as pd
import numpy as np

# 1. 데이터 로드 (엑셀)
df = pd.read_excel('스프린트 테스트결과.xlsx')
df['score'] = pd.to_numeric(df['리스크점수(AI)'], errors='coerce').fillna(0)
actual = df['원본_위험도(정답)'].values
scores = df['score'].values

def evaluate_thresholds(t1, t2):
    preds = []
    for s in scores:
        if s < t1: preds.append('안전')
        elif s < t2: preds.append('주의')
        else: preds.append('위험')
    
    preds = np.array(preds)
    labels = ['안전', '주의', '위험']
    recalls = {label: np.sum((actual == label) & (preds == label)) / np.sum(actual == label) 
               if np.sum(actual == label) > 0 else 0 for label in labels}
    
    return recalls, np.sum(actual == preds) / len(actual)

# 모든 조합 시뮬레이션
combinations = []
for t1 in range(0, 101):
    for t2 in range(t1 + 1, 101):
        recalls, acc = evaluate_thresholds(t1, t2)
        combinations.append({
            't1': t1, 't2': t2,
            'safe': recalls['안전'],
            'caution': recalls['주의'],
            'risk': recalls['위험'],
            'acc': acc
        })

# 2. 묶음별 최적 순서쌍 찾기
# (두 등급의 합산 적중률이 같을 경우, 전체 정확도(acc)가 높은 순)

# Case A: [안전 + 주의] 적중률 극대화 (일반 광고주 보호 중심)
best_safe_caution = max(combinations, key=lambda x: (x['safe'] + x['caution'], x['acc']))

# Case B: [안전 + 위험] 적중률 극대화 (양극단 판별 중심 - 중간층은 포기)
best_safe_risk = max(combinations, key=lambda x: (x['safe'] + x['risk'], x['acc']))

# Case C: [주의 + 위험] 적중률 극대화 (리스크 관리 강화 중심)
best_caution_risk = max(combinations, key=lambda x: (x['caution'] + x['risk'], x['acc']))

# 3. 결과 출력
print("="*60)
print("📊 등급 결합형(Combined) 최적 임계값 리포트")
print("="*60)

for title, res in [("🟢+🟡 [안전/주의] 결합 최적", best_safe_caution), 
                   ("🟢+🔴 [안전/위험] 결합 최적", best_safe_risk), 
                   ("🟡+🔴 [주의/위험] 결합 최적", best_caution_risk)]:
    print(f"\n▶ {title}")
    print(f"   - 임계값: (t1: {res['t1']}, t2: {res['t2']})")
    print(f"   - 적중률: 안전({res['safe']:.1%}), 주의({res['caution']:.1%}), 위험({res['risk']:.1%})")
    print(f"   - 결합 합계: { (res['safe'] + res['caution'] if '안전/주의' in title else (res['safe'] + res['risk'] if '안전/위험' in title else res['caution'] + res['risk'])):.1%}")
    print(f"   - 전체 정확도: {res['acc']:.1%}")