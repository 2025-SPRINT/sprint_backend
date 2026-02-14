import asyncio
import os
import json
from datetime import datetime
from google import genai
from google.genai import types
from typing import Literal, List, Optional
from typing_extensions import TypedDict
from dotenv import load_dotenv
from mcp_connector import get_singleton_connector
from utils.profiler import trace, profiler
import time

# --- Configuration ---
USE_JSON_OUTPUT = True  # Set to True to enable JSON structured output
# ---------------------

class GeminiDebugLogger:
    def __init__(self):
        self.steps = []
        self.gemini_api_call_count = 0
        self.kipris_api_call_count = 0
        self.start_time = datetime.now()
        self.total_tokens = None

    def log_api_call(self, role, content=None, function_calls=None):
        if role == "model":
            self.gemini_api_call_count += 1
        
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "function_calls": function_calls,
            "turn": self.gemini_api_call_count if role == "model" else 0
        }
        self.steps.append(entry)

    def log_tool_result(self, tool_name, result):
        self.kipris_api_call_count += 1
        self.steps.append({
            "role": "tool",
            "tool_name": tool_name,
            "result": result,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "turn": self.gemini_api_call_count
        })

    def set_usage(self, usage):
        self.total_tokens = usage

    def generate_report(self):
        report = [
            "# Gemini API Flow Debug Log",
            f"- **Date**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Total Gemini API Calls**: {self.gemini_api_call_count}",
        ]
        
        if self.total_tokens:
            report.append(f"- **Token Usage**: Prompt: {self.total_tokens.prompt_token_count}, Candidates: {self.total_tokens.candidates_token_count}, Total: {self.total_tokens.total_token_count}")
        
        # Add Performance Profiling Section
        from utils.profiler import profiler
        performance_data = profiler.data
        if performance_data:
            report.append("\n## ⏱️ Performance Analysis")
            report.append("| Component / Function | Calls | Total Time |")
            report.append("| :--- | :---: | :---: |")
            # Sort by duration descending
            sorted_items = sorted(performance_data.items(), key=lambda x: x[1]['total_time'], reverse=True)
            for name, stats in sorted_items:
                report.append(f"| {name} | {stats['calls']} | {stats['total_time']:.4f}s |")
        
        report.append("\n## 💬 Communication Flow\n")
        
        for step in self.steps:
            role = step['role']
            time = step['timestamp']
            
            if role == "user":
                report.append(f"### 👤 User (Input) *[{time}]*")
                report.append(f"```text\n{step['content']}\n```\n")
            
            elif role == "model":
                turn_label = f" (Turn {step['turn']})" if step['turn'] > 0 else ""
                report.append(f"### 🤖 Gemini Response{turn_label} *[{time}]*")
                
                # Show text part if exists
                if step['content']:
                    report.append(f"**Thought/Draft**:\n\n{step['content']}\n")
                
                # Show function calls if exists
                if step['function_calls']:
                    report.append("#### 🛠️ Tool Usage (Function Calls)")
                    for fc in step['function_calls']:
                        args_json = json.dumps(fc.args, indent=2, ensure_ascii=False)
                        report.append(f"- **Tool**: `{fc.name}`")
                        report.append(f"- **Arguments**:\n```json\n  {args_json}\n```")
                report.append("---")

            elif role == "tool":
                report.append(f"### 📥 Tool Result (`{step['tool_name']}`) *[{time}]*")
                # Truncate very long tool results for readability
                res_str = str(step['result'])
                if len(res_str) > 2000:
                    res_str = res_str[:2000] + "... (truncated)"
                report.append(f"```json\n{res_str}\n```\n")

        return "\n".join(report)

    def save(self, folder="debug"):
        if not os.path.exists(folder):
            os.makedirs(folder)
        
        filename = f"api_flow_{self.start_time.strftime('%Y%m%d_%H%M%S')}.md"
        path = os.path.join(folder, filename)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.generate_report())
        
        return path

# PROMPT_1 with patent grounding instructions
PROMPT_1 = """
1. 당신은 광고 신뢰성 분석의 전문가입니다. 사용자로부터 받은 광고의 스크립트를 분석하여 광고와 제품의 신뢰성을 평가합니다. 사용자는 유튜브 쇼츠에서 시청한 광고의 스크립트를 제공합니다. 평가한 결과를 사용자에게 전달해야 합니다.

2. 광고 신뢰성 분석을 통해 광고가 과장되었는지, 사실에 기반했는지, 또는 오해의 소지가 있는지를 평가합니다. 
광고에서 제품에 대한 특허를 언급하는 부분이 있다면, 제공된 'patent_search' 또는 'patent_keyword_search' 등 KIPRIS 관련 도구를 사용하여 해당 특허가 실제로 존재하는지 반드시 확인하세요. 
또한 일반적인 정보 확인을 위해 "Google 검색 그라운딩"도 함께 활용하세요.

3. 답변은 텍스트 형식으로 제공하세요.

4. 답변은 전문적이고 간결한 어조로 설명하세요. 답변은 사용자에게 전달됩니다. 온화한 어조를 유지하세요.

5. 사용자는 디지털 정보에 취약한 고령자, 또는 광고에 쉽게 현혹되는 일반 소비자, 또는 청소년일 수 있습니다. 이 점을 고려하여 답변을 작성하세요.

6. 광고 스크립트를 바탕으로 다음과 같은 답변 형식을 제공하세요.
 - 광고의 신뢰성을 범주화하여 제시하세요(위험, 안전, 주의).
 - 광고 스크립트의 문제점을 간략화해서 제시하세요.
 - ***광고에서 특허에 대한 언급이 있을 때에만*** KIPRIS 도구를 통해 확인한 특허 정보(존재 여부, 특허 번호, 출원인 등)를 상세히 제시하세요.
 - 검색 그라운딩으로 확인한 정보는 출처와 함께 제시하세요(링크 포함).

7. 이후 내용은 광고 스크립트입니다. 스크립트를 기반으로 위 지시사항에 따라 답변을 작성하세요.
"""

PROMPT_2 = """
# Role: 광고 신뢰성 및 과학적 타당성 분석 전문가

## 1. 분석 미션
사용자가 제공한 유튜브 쇼츠 광고 스크립트를 분석하여 제품의 신뢰성을 [위험], [주의], [안전]으로 분류하고, 의학적/기술적 허위 사실을 검증합니다. 특히 디지털 정보에 취약한 고령자나 청소년이 이해하기 쉽게 친절하면서도 전문적인 어조를 유지하세요.

## 2. 핵심 검증 로직 (검색 전략)
검색 시 다음 단계를 반드시 준수하여 '결과 없음' 오류를 최소화하세요.

### STEP 1: 키워드 다변화 (KIPRIS 및 Google 검색 시 적용)
- **제품명 검색 실패 시:** 광고에 언급된 '핵심 성분(예: IGF-1)', '핵심 기술(예: 경구 흡수)', '제조사'를 조합하여 재검색하세요.
- **특허 검증:** "유럽 특허"라고 주장할 경우, 한국 특허청(KIPRIS)에 등록된 '외국 도입 특허' 또는 '해외 출원인' 명의의 특허를 검색하세요.
- **식약처 검증:** "식약처 인증" 언급 시, 실제 '건강기능식품'인지 단순 '기타가공품'인지 분류를 확인하세요.

### STEP 2: 과학적 반증 (Logical Reasoning)
- 광고의 주장이 보편적인 과학 상식(예: 단백질은 위에서 분해됨)과 배치될 경우, 이를 극복했다는 '구체적인 기술적 근거(특허 번호 등)'가 검색되지 않는다면 이를 [위험] 요소로 간주하세요.

## 3. 답변 형식 (필수 포함 사항)

### [광고 신뢰성 등급]
- **등급:** [위험 / 주의 / 안전] 중 택 1
- **한 줄 요약:** 소비자에게 가장 치명적인 문제점을 한 줄로 요약.

### 광고 스크립트의 주요 문제점
- 일반 소비자가 현혹되기 쉬운 '심리적 기만 요소'와 '의학적 왜곡 사항'을 번호를 매겨 설명하세요.

### 특허 및 인증 정보 상세 (KIPRIS/식약처)
- **특허 존재 여부:** 존재/미확인/허위 (미확인 시 "해당 기술로 등록된 국내외 특허를 찾을 수 없음" 명시)
- **상세 정보:** 특허 번호, 출원인, 발명 명칭 등 (검색된 경우에만 작성)
- **인증 사실:** 식약처 건강기능식품 데이터베이스 조회 결과

### 검색 그라운딩 및 전문가 견해 (출처 포함)
- 공신력 있는 기관(대한의사협회, 식약처, 소비자원 등)의 보도자료나 논문 근거를 제시하세요.
- 확인된 정보는 반드시 해당 페이지 링크를 포함하세요.

---
## 4. 분석 시작 (입력된 스크립트 처리)
이후 입력되는 [광고 스크립트]에 대해 위 가이드라인에 따라 분석 보고서를 작성하세요.
"""

PROMPT_3 = """
# Role: 광고 신뢰성 및 과학적 타당성 분석 전문가

## 1. 분석 미션
사용자가 제공한 유튜브 쇼츠 광고 스크립트를 분석하여 제품의 신뢰성을 [위험], [주의], [안전]으로 분류하고, 의학적/기술적 허위 사실을 검증합니다. 특히 디지털 정보에 취약한 고령자나 청소년이 이해하기 쉽게 친절하면서도 전문적인 어조를 유지하세요.

## 2. 핵심 검증 로직 (검색 전략)
검색 시 다음 단계를 반드시 준수하여 '결과 없음' 오류를 최소화하세요.

### STEP 1: 키워드 다변화 (KIPRIS 및 Google 검색 시 적용)
- **주의사항:** KIPRIS는 특허청에 등록된 특허를 검색하는 API 서비스입니다. 정확한 특허를 찾기 위해서는 일반적인 검색어와 다른, 전문적인 키워드와 어조를 유지해야 합니다.
    - 다음은 KIPRIS에 등록된 특허의 예시입니다. 예시를 바탕으로 키워드의 특징을 분석하고 검색할 키워드를 신중히 생성하세요.
    - 예1: 인삼 열매 추출물을 함유하는 성장촉진용 조성물(Composition for accelerating the growth containing ginseng berry extracts)
    - 예2: 백수오 및 한속단 추출복합물을 포함하는 성장촉진 조성물의 제조방법(Manufacturing method of Composition for Promoting Growth comprising Extract of Cynanchum Wilfordii and Phlomis umbrosa)
    - 예3: 인공지능 기반의 의료 데이터 중개 서비스 제공 방법, 서버 및 프로그램(Method, server and program for providing medical data brokerage services based on AI)
    - 예4: 전술벨트 장착이 용이한 프리벨트 군용바지(TROUSERS OF MILITARY UNIFORM)
    - 예5: ROTATING MACHINE VIBRATION MONITORING PROCESS FOR DETECTING DEGRADATIONS WITHIN A ROTATING MACHINE FITTED WITH MAGNETIC BEARINGS
- **제품명 검색 실패 시:** 광고에 언급된 '핵심 성분(예: IGF-1)', '핵심 기술(예: 경구 흡수)', '제조사'를 조합하여 재검색하세요.
- **특허 검증:** "유럽 특허"라고 주장할 경우, 한국 특허청(KIPRIS)에 등록된 '외국 도입 특허' 또는 '해외 출원인' 명의의 특허를 검색하세요.
- **식약처 검증:** "식약처 인증" 언급 시, 실제 '건강기능식품'인지 단순 '기타가공품'인지 분류를 확인하세요.

### STEP 2: 과학적 반증 (Logical Reasoning)
- 광고의 주장이 보편적인 과학 상식(예: 단백질은 위에서 분해됨)과 배치될 경우, 이를 극복했다는 '구체적인 기술적 근거(특허 번호 등)'가 검색되지 않는다면 이를 [위험] 요소로 간주하세요.

## 3. 답변 형식 (필수 포함 사항)

### [광고 신뢰성 등급]
- **등급:** [위험 / 주의 / 안전] 중 택 1
- **한 줄 요약:** 소비자에게 가장 치명적인 문제점을 한 줄로 요약.

### 광고 스크립트의 주요 문제점
- 일반 소비자가 현혹되기 쉬운 '심리적 기만 요소'와 '의학적 왜곡 사항'을 번호를 매겨 설명하세요.

### 특허 및 인증 정보 상세 (KIPRIS/식약처)
- **특허 존재 여부:** 존재/미확인/허위 (미확인 시 "해당 기술로 등록된 국내외 특허를 찾을 수 없음" 명시)
- **상세 정보:** 특허 번호, 출원인, 발명 명칭 등 (검색된 경우에만 작성)
- **인증 사실:** 식약처 건강기능식품 데이터베이스 조회 결과

### 검색 그라운딩 및 전문가 견해 (출처 포함)
- 공신력 있는 기관(대한의사협회, 식약처, 소비자원 등)의 보도자료나 논문 근거를 제시하세요.
- 확인된 정보는 반드시 해당 페이지 링크를 포함하세요.

---
## 4. 분석 시작 (입력된 스크립트 처리)
이후 입력되는 [광고 스크립트]에 대해 위 가이드라인에 따라 분석 보고서를 작성하세요.
"""

PROMPT_4 = """
# Role: 광고 신뢰성 및 과학적 타당성 분석 전문가

## 1. 분석 미션
사용자가 제공한 유튜브 쇼츠 광고 스크립트를 분석하여 제품의 신뢰성을 [위험], [주의], [안전]으로 분류하고, 의학적/기술적 허위 사실을 검증합니다. 특히 디지털 정보에 취약한 고령자나 청소년이 이해하기 쉽게 친절하면서도 전문적인 어조를 유지하세요.

## 2. 핵심 검증 로직 (검색 전략)
***광고에서 '특허'와 관련된 언급이 있을 때만 반드시 다음 전략을 사용해 해당 특허 언급이 진짜인지 검증하세요.***

### STEP 1: 키워드 다변화 (KIPRIS 및 Google 검색 시 적용)
- **주의사항:** KIPRIS는 특허청에 등록된 특허를 검색하는 API 서비스입니다. 정확한 특허를 찾기 위해서는 일반적인 검색어와 다른, 전문적인 키워드와 어조를 유지해야 합니다.
    - 다음은 KIPRIS에 등록된 특허의 예시입니다. 예시를 바탕으로 키워드의 특징을 분석하고 검색할 키워드를 신중히 생성하세요.
    - 예1: 인삼 열매 추출물을 함유하는 성장촉진용 조성물(Composition for accelerating the growth containing ginseng berry extracts)
    - 예2: 백수오 및 한속단 추출복합물을 포함하는 성장촉진 조성물의 제조방법(Manufacturing method of Composition for Promoting Growth comprising Extract of Cynanchum Wilfordii and Phlomis umbrosa)
    - 예3: 인공지능 기반의 의료 데이터 중개 서비스 제공 방법, 서버 및 프로그램(Method, server and program for providing medical data brokerage services based on AI)
    - 예4: 전술벨트 장착이 용이한 프리벨트 군용바지(TROUSERS OF MILITARY UNIFORM)
    - 예5: ROTATING MACHINE VIBRATION MONITORING PROCESS FOR DETECTING DEGRADATIONS WITHIN A ROTATING MACHINE FITTED WITH MAGNETIC BEARINGS
- **제품명 검색 실패 시:** 광고에 언급된 '핵심 성분(예: IGF-1)', '핵심 기술(예: 경구 흡수)', '제조사'를 조합하여 재검색하세요.
- **특허 검증:** "유럽 특허"라고 주장할 경우, 한국 특허청(KIPRIS)에 등록된 '외국 도입 특허' 또는 '해외 출원인' 명의의 특허를 검색하세요.
- **식약처 검증:** "식약처 인증" 언급 시, 실제 '건강기능식품'인지 단순 '기타가공품'인지 분류를 확인하세요.

### STEP 2: 과학적 반증 (Logical Reasoning)
- 광고의 주장이 보편적인 과학 상식(예: 단백질은 위에서 분해됨)과 배치될 경우, 이를 극복했다는 '구체적인 기술적 근거(특허 번호 등)'가 검색되지 않는다면 이를 [위험] 요소로 간주하세요.

## 3. 답변 형식 (필수 포함 사항)

### [광고 신뢰성 등급]
- **등급:** [위험 / 주의 / 안전] 중 택 1
- **한 줄 요약:** 소비자에게 가장 치명적인 문제점을 한 줄로 요약.

### 광고 스크립트의 주요 문제점
- 일반 소비자가 현혹되기 쉬운 '심리적 기만 요소'와 '의학적 왜곡 사항'을 번호를 매겨 설명하세요.

### 특허 및 인증 정보 상세 (KIPRIS/식약처)
- **특허 존재 여부:** 존재/미확인/허위 (미확인 시 "해당 기술로 등록된 국내외 특허를 찾을 수 없음" 명시)
- **상세 정보:** 특허 번호, 출원인, 발명 명칭 등 (검색된 경우에만 작성)
- **인증 사실:** 식약처 건강기능식품 데이터베이스 조회 결과

### 검색 그라운딩 및 전문가 견해 (출처 포함)
- 공신력 있는 기관(대한의사협회, 식약처, 소비자원 등)의 보도자료나 논문 근거를 제시하세요.
- 확인된 정보는 반드시 해당 페이지 링크를 포함하세요.

---
## 4. 분석 시작 (입력된 스크립트 처리)
이후 입력되는 [광고 스크립트]에 대해 위 가이드라인에 따라 분석 보고서를 작성하세요.
"""

PROMPT_5 = """
# Role
당신은 공정하고 객관적인 '광고 신뢰성 분석가'입니다. 귀하의 목표는 제공된 광고 스크립트의 주장을 검증하여, 소비자가 올바른 판단을 내릴 수 있도록 사실에 입각한 분석 리포트를 제공하는 것입니다.

# Principles
1. **중립성 유지**: 광고가 무조건 거짓이라거나, 무조건 진실이라고 예단하지 마십시오. 오직 '검증된 증거'에 기반하여 판단하십시오.
2. **증거 기반 평가 (Evidence-Based)**: 모든 평가는 KIPRIS(특허) 및 Google 검색(일반 정보) 결과에 근거해야 합니다. 추측에 의한 평가는 금지합니다.
3. **환각 방지 (Chain of Thought)**: 즉시 결론을 내리지 말고, 반드시 [주장 식별 -> 검증 수행 -> 결과 비교 -> 최종 평가]의 사고 과정을 거치십시오.

# Process (Thinking Flow)
분석은 반드시 다음 순서로 진행하십시오:

1. **주장 식별 (Claims Extraction)**: 광고 스크립트에서 검증이 필요한 핵심 주장(특허 번호, 기술명, 효과 통계, 인증 여부 등)을 추출합니다.
2. **사실 검증 (Verification)**:
   - '특허', '출원', '기술' 언급 시: 제공된 KIPRIS 도구를 사용하여 실제 등록 여부와 내용을 확인합니다. (유사 키워드로도 검색 시도할 것)
   - 일반 주장 및 인증 언급 시: Google 검색 그라운딩을 통해 해당 제품/성분의 효능, 식약처 인증 여부, 관련 뉴스를 확인합니다.
3. **비교 및 평가 (Evaluation)**: 광고의 주장과 검색된 사실이 일치하는지 비교합니다.
   - 일치: '신뢰할 수 있음'
   - 부분 일치/과장: '주의 필요' (사실과 다른 부분 명시)
   - 불일치/거짓: '위험/허위' (검색되지 않거나 사실과 정반대임)
4. **리포트 작성 (Report Generation)**: 위 평가를 바탕으로 최종 사용자에게 전달할 보고서를 작성합니다.

# Output Format
보고서는 디지털 정보 취약 계층(고령자, 청소년 등)도 이해하기 쉬운 친절하고 명확한 어조로 작성하십시오.

1. **종합 평가 등급**: [안전 / 주의 / 위험 / 정보 부족] 중 하나를 선택하고, 그 이유를 한 문장으로 요약합니다.
2. **주요 검증 결과**:
   - 광고 문구: "광고에서 주장하는 문장"
   - 검증된 사실: 검색을 통해 확인된 객관적 사실
   - 판단 근거: (특허 검색 결과 또는 구글 검색 출처)
3. **특허/인증 정밀 분석** (해당되는 경우만 작성):
   - 언급된 특허가 실제로 존재하는지, 광고하는 효능과 일치하는 특허인지 명시합니다. KIPRIS 도구 사용 결과를 구체적으로 기술하십시오.
4. **소비자 가이드**: 소비자가 유의해야 할 점이나 전문가적 조언을 제공합니다.

# Context
이후 내용은 사용자가 시청한 유튜브 쇼츠 광고의 스크립트입니다. 위 지침을 준수하여 분석하십시오.
"""

PROMPT_6 = """
# Role
당신은 공정하고 객관적인 '광고 신뢰성 분석가'입니다. 귀하의 목표는 제공된 광고 스크립트의 주장을 검증하여, 소비자가 올바른 판단을 내릴 수 있도록 사실에 입각한 분석 리포트를 제공하는 것입니다.

# Principles
1. **중립성 유지**: 광고가 무조건 거짓이라거나, 무조건 진실이라고 예단하지 마십시오. 오직 '검증된 증거'에 기반하여 판단하십시오.
2. **증거 기반 평가 (Evidence-Based)**: 모든 평가는 KIPRIS(특허) 및 Google 검색(일반 정보) 결과에 근거해야 합니다. 추측에 의한 평가는 금지합니다.
3. **환각 방지 (Chain of Thought)**: 즉시 결론을 내리지 말고, 반드시 [주장 식별 -> 검증 수행 -> 결과 비교 -> 최종 평가]의 사고 과정을 거치십시오.

# Process (Thinking Flow)
분석은 반드시 다음 순서로 진행하십시오:

1. **주장 식별 (Claims Extraction)**: 광고 스크립트에서 검증이 필요한 핵심 주장(특허 번호, 기술명, 효과 통계, 인증 여부 등)을 추출합니다.
2. **사실 검증 (Verification)**:
   - '특허', '출원', '기술' 언급 시: 제공된 KIPRIS 도구를 사용하여 실제 등록 여부와 내용을 확인합니다. (유사 키워드로도 검색 시도할 것)
   - 일반 주장 및 인증 언급 시: Google 검색 그라운딩을 통해 해당 제품/성분의 효능, 식약처 인증 여부, 관련 뉴스를 확인합니다.
3. **비교 및 평가 (Evaluation)**: 광고의 주장과 검색된 사실이 일치하는지 비교합니다.
   - 일치: '신뢰할 수 있음'
   - 부분 일치/과장: '주의 필요' (사실과 다른 부분 명시)
   - 불일치/거짓: '위험/허위' (검색되지 않거나 사실과 정반대임)
4. **결과 생성 (JSON Generation)**: 위 평가를 바탕으로 주어진 JSON Schema에 맞춰 결과를 생성합니다.

# Output Guidelines
- `reliability_level`: "안전", "주의", "위험", "정보 부족" 중 하나 선택.
- `summary`: 소비자에게 가장 치명적인 문제점을 한 줄로 요약.
- `issues`: 일반 소비자가 현혹되기 쉬운 심리적 기만 요소나 의학적 왜곡 사항을 리스트로 작성.
- `patent_check`: 특허 관련 언급이 있을 경우 상세 분석. 없으면 `status`를 "해당 없음"으로 표기.
- `evidence`: 검색을 통해 확인된 객관적 근거들.
- `consultation`: 소비자가 유의해야 할 점이나 전문가적 조언. 친절하고 명확한 어조.

# Context
이후 내용은 사용자가 시청한 유튜브 쇼츠 광고의 스크립트입니다. 위 지침을 준수하여 분석하십시오.
"""

# --- JSON Schemas ---
class PatentCheck(TypedDict):
    status: Literal["존재", "미확인", "허위", "해당 없음"]
    details: str
    patent_number: Optional[str]

class EvidenceItem(TypedDict):
    source: str
    url: Optional[str]
    fact: str

class AdAnalysisResult(TypedDict):
    reliability_level: Literal["안전", "주의", "위험", "정보 부족"]
    summary: str
    issues: List[str]
    patent_check: PatentCheck
    evidence: List[EvidenceItem]
    consultation: str
# --------------------

SCRIPT = "아니, 아직도 안 믿으세요. 비문증 방치하면 실명이라니까요. 제가 김포에서 초등부 야구 감독으로 15년째인데요. 어느 날 연습 중에 애가 던진 공에 눈을 정통으로 맞은 거예요. 그때 치료 잘 받고 괜찮아졌다고 생각했는데 며칠 뒤부터 눈앞에 계속 날파리 같은게 떠다니는 거예요. 알고 보니 이게 눈 안에 무슨 유리채 찔꺼기가 뭉친 비문증이라요. 처음엔 시간 지나면 없어지겠지 했는데 경험 갔더니 실명 직전 남결합니다. 애들 가르치는 사람인데 실명이라니 순간 숨이 턱 막히더라고요. 그래서 제가 단원합니다. 이거 방치하면 막막 찢어지고 실명업입니다. 실명. 그런데 이거 먹고도 그대로면 제가 전재산 드리겠습니다. 딱 일주일만 먹어 보세요. 이건 진짜 국내 최초로 유일하게 비문개 선택을 받은 비문증 치료제예요. 다른 거랑은 비교도 하지 마세요. 하루에 한 번만 챙겨 드세요. 얼마나 편해요?이 좋은 걸 꾸준히 먹기만 하면 실명을 안 한다는데. 그리고 지금 아니면 고압량 제고는 구하지도 못해요. 3일루 후에 고압량 제거 단종된다고 공식 발표는 미루면 진짜 끝납니다."

PROMPT_6 = """
# Role
당신은 대한민국 '표시·광고에 관한 법률' 및 '식약처 광고 심의 가이드라인'을 준수하는 공정하고 객관적인 '광고 신뢰성 분석가'입니다. 귀하의 목표는 제공된 광고 스크립트의 주장을 검증하여, 소비자가 올바른 판단을 내릴 수 있도록 사실에 입각한 **간결한** 분석 리포트를 제공하는 것입니다.

# Principles
1. **중립성 유지**: 광고가 무조건 거짓이라거나, 무조건 진실이라고 예단하지 마십시오. 오직 '검증된 증거'에 기반하여 판단하십시오.
2. **증거 기반 평가 (Evidence-Based)**: 모든 평가는 KIPRIS(특허) 및 Google 검색(일반 정보) 결과에 근거해야 합니다. 추측에 의한 평가는 금지합니다.
3. **환각 방지 (Chain of Thought)**: 즉시 결론을 내리지 말고, 반드시 [주장 식별 -> 검증 수행 -> 결과 비교 -> 최종 평가]의 사고 과정을 거치십시오.
4. **간결성 (Brevity)**: 모든 출력은 최대한 간결하게 작성하십시오. 프론트엔드에서 표시하기 용이하도록 불필요한 수식어나 반복을 피하십시오.
5. 모든 광고는 100점에서 시작하며, 아래 위반 항목 발견 시 감점하여 최종 등급('reliability_level')을 결정하십시오.

# Process (Thinking Flow)
분석은 반드시 다음 순서로 진행하십시오:

1. **주장 식별 (Claims Extraction)**: 광고 스크립트에서 검증이 필요한 핵심 주장(특허 번호, 기술명, 효과 통계, 인증 여부 등)을 추출합니다.
2. **사실 검증 (Verification)**:
   - **특허 관련 언급이 있을 때만**: 제공된 KIPRIS 도구를 사용하여 실제 등록 여부와 내용을 확인합니다. (유사 키워드로도 검색 시도할 것)
   - **특허 언급이 없으면**: KIPRIS 검색을 생략하고 `patent_check`를 `null`로 반환합니다.
   - 일반 주장 및 인증 언급 시: Google 검색 그라운딩을 통해 해당 제품/성분의 효능, 식약처 인증 여부, 관련 뉴스를 확인합니다.
3. **결과 매핑 및 감점 (Mapping & Scoring)**:
   - **[검증 실패]** 주장한 특허/인증이 허위이거나 검색되지 않을 경우: **즉시 -50점 (위험)**
   - **[의학적 과장]** 식품임에도 질병 치료 효능이 확인된 사실처럼 주장할 경우: **즉시 -50점 (위험)**
   - **[근거 없는 확언]** "전재산을 주겠다" 등 검증 불가능한 보장을 할 경우: **즉시 -30점 (위험)**
   - **[최상급 표현]** "국내 유일", "최초" 등이 검색 결과로 증명되지 않을 경우: **-20점 (주의)**
   - **[심리적 기만]** "단종 예정" 등이 공식 정보와 다를 경우: **-15점 (주의)**
4. **결과 생성 (JSON Generation)**: 위 평가를 바탕으로 주어진 JSON Schema에 맞춰 결과를 생성합니다.

# Output Guidelines (간결성 필수)
- `reliability_level`: "안전", "주의", "위험", "정보 부족" 중 하나 선택.(0~50:위험 / 51~80:주의 / 81~100:안전)
2. `summary`: 광고의 핵심 기만 수법과 그 이유를 결합하여 **한 문장**으로 요약. (최대 50자 권장)
   - 형식: "[기만수법] 때문이며, 이는 [검증결과]와 대조되어 위험합니다."
   - 예시: "허위 특허 주장(비문증 치료제 미등록) 및 실명 공포 마케팅으로 인한 위험 등급입니다."
3. `issues`: 광고의 문제점을 소비자가 즉각 인지하도록 **[수법: 구체적 사유]** 형식으로 작성. (항목당 20자 내외)
   - 예시 1: "[허위특허] 치료제 등록 내역 없음"
   - 예시 2: "[공포조장] 방치 시 실명한다며 위협"
   - 예시 3: "[허위보장] 전재산 건다는 비과학적 확언"
- `patent_check`: **광고에 특허 관련 언급이 있을 경우에만** 작성. 특허 언급이 없으면 반드시 `null`로 설정.
- `evidence`: 검색을 통해 확인된 핵심 근거만 간략히. 각 `fact`는 1-2문장.
- `consultation`: **1-2문장**으로 핵심 조언만 제공. 장황한 설명 금지.

# Context
이후 내용은 사용자가 시청한 유튜브 쇼츠 광고의 스크립트입니다. 위 지침을 준수하여 분석하십시오.
"""

# --- JSON Schemas ---
class PatentCheck(TypedDict):
    status: Literal["존재", "미확인", "허위", "해당 없음"]
    details: str
    patent_number: Optional[str]

class EvidenceItem(TypedDict):
    source: str
    url: Optional[str]
    fact: str

class AdAnalysisResult(TypedDict):
    reliability_level: Literal["안전", "주의", "위험", "정보 부족"]
    summary: str
    issues: List[str]
    patent_check: Optional[PatentCheck]  # 특허 언급 없으면 null
    evidence: List[EvidenceItem]
    consultation: str
# --------------------

@trace("Gemini Analysis (Full)")
async def main(prompt, script):
    load_dotenv()
    api_key = os.getenv("API_KEY")
    client = genai.Client(api_key=api_key)

    # 1. Start KIPRIS MCP Connector (싱글톤 사용으로 재사용)
    connector, kipris_tools = await get_singleton_connector()


    # 2. Add Google Search grounding tool
    google_search_tool = types.Tool(google_search=types.GoogleSearch())
    
    # 3. Combine tools
    # Attempting to combine both into a single Tool object to avoid compatibility issues
    
    if USE_JSON_OUTPUT:
        target_prompt = PROMPT_6
        # Configure for JSON output
        config = types.GenerateContentConfig(
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch(),
                    function_declarations=kipris_tools
                )
            ],
            response_mime_type="application/json",
            response_schema=AdAnalysisResult
        )
        print("모드: JSON 구조화 출력 (PROMPT_6)")
    else:
        target_prompt = PROMPT_5
        # Original configuration
        config = types.GenerateContentConfig(
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch(),
                    function_declarations=kipris_tools
                )
            ]
        )
        print("모드: 일반 텍스트 출력 (PROMPT_5)")

    full_prompt = f"{target_prompt}\n\n[광고 스크립트]:\n{script}"
    history = [types.Content(role="user", parts=[types.Part(text=full_prompt)])]

    # Init Logger
    logger = GeminiDebugLogger()
    logger.log_api_call("user", full_prompt)

    print("Gemini에게 요청을 보내는 중(KIPRIS + Google Search)...")
    
    try:
        # Initial call
        start_api = time.perf_counter()
        response = client.models.generate_content(
            model="gemini-3-flash-preview", 
            contents=history,
            config=config
        )
        profiler.log_manual("Gemini API: First Call", time.perf_counter() - start_api)
        
        # Log first model response
        res_text = response.text if response.candidates[0].content.parts and any(p.text for p in response.candidates[0].content.parts) else "[Tool Call Only]"
        logger.log_api_call("model", res_text, 
                           function_calls=[p.function_call for p in response.candidates[0].content.parts if p.function_call])

        max_turns = 10
        turn_count = 0
        total_usage = response.usage_metadata
        current_response = response

        while turn_count < max_turns and current_response.candidates[0].content.parts and any(p.function_call for p in current_response.candidates[0].content.parts):
            turn_count += 1
            # Add model's response to history
            history.append(current_response.candidates[0].content)
            
            tool_parts = []
            for part in current_response.candidates[0].content.parts:
                if part.function_call:
                    name = part.function_call.name
                    args = part.function_call.args
                    
                    # 1. Skip non-MCP tools (like google_search)
                    # These are handled by Gemini and should not be passed to the MCP connector.
                    if name == "google_search":
                        print(f"로그: 내장 도구 발견(스킵) - {name}")
                        continue

                    print(f"로그: MCP 도구 호출 중 - {name}({args})")
                    
                    # 2. Execute MCP tool
                    try:
                        start_tool = time.perf_counter()
                        result = await connector.call_tool(name, args)
                        profiler.log_manual(f"KIPRIS Tool: {name}", time.perf_counter() - start_tool)
                        
                        content_text = "\n".join([c.text for c in result.content if hasattr(c, 'text')]) if hasattr(result, 'content') else str(result)
                        logger.log_tool_result(name, content_text)
                        tool_parts.append(types.Part.from_function_response(name=name, response={"result": content_text}))
                    except Exception as e:
                        print(f"도구 호출 오류 ({name}): {e}")
                        tool_parts.append(types.Part.from_function_response(name=name, response={"error": str(e)}))
            
            if tool_parts:
                history.append(types.Content(role="tool", parts=tool_parts))
                start_api = time.perf_counter()
                current_response = client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=history,
                    config=config
                )
                profiler.log_manual(f"Gemini API: Turn {turn_count+1}", time.perf_counter() - start_api)
                
                if current_response.usage_metadata:
                    total_usage.prompt_token_count += current_response.usage_metadata.prompt_token_count
                    total_usage.candidates_token_count += current_response.usage_metadata.candidates_token_count
                    total_usage.total_token_count += current_response.usage_metadata.total_token_count

                inner_text = current_response.text if current_response.candidates[0].content.parts and any(p.text for p in current_response.candidates[0].content.parts) else "[Tool Call Only]"
                logger.log_api_call("model", inner_text,
                                   function_calls=[p.function_call for p in current_response.candidates[0].content.parts if p.function_call])
            else:
                # If tool_parts is empty (e.g., only google_search was called), 
                # we break the loop to avoid an empty request.
                break
        
        if turn_count >= max_turns:
            print(f"경고: 최대 도구 호출 횟수({max_turns})에 도달하여 루프를 종료합니다.")

        final_text = current_response.text if current_response.candidates[0].content.parts and any(p.text for p in current_response.candidates[0].content.parts) else "분석 결과를 생성하지 못했습니다."
        print("\n[최종 분석 결과]\n")
        
        if USE_JSON_OUTPUT:
            try:
                # Pretty print JSON
                json_data = json.loads(final_text)
                print(json.dumps(json_data, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print("JSON 파싱 실패:")
                print(final_text)
        else:
            print(final_text)
            
        print("\n" + "="*50 + "\n")

        # Citation handling
        text_with_citations = add_citations(current_response)
        
        # Finalize Usage and Log
        logger.set_usage(total_usage)
        debug_path = logger.save()
        print(f"\n[Debug] 상세 API 호출 흐름이 저장되었습니다: {debug_path}")

        save_response_to_file(total_usage, PROMPT_1, text_with_citations)

        return final_text
    finally:
        await connector.disconnect()
        print("로그: MCP 커넥터가 종료되었습니다.")


def add_citations(response):
    text = response.text
    if not response.candidates[0].grounding_metadata:
        return text
    
    metadata = response.candidates[0].grounding_metadata
    if not hasattr(metadata, 'grounding_supports') or not metadata.grounding_supports:
        return text

    supports = metadata.grounding_supports
    chunks = metadata.grounding_chunks

    sorted_supports = sorted(supports, key=lambda s: s.segment.end_index, reverse=True)

    for support in sorted_supports:
        end_index = support.segment.end_index
        if support.grounding_chunk_indices:
            citation_links = []
            for i in support.grounding_chunk_indices:
                if i < len(chunks):
                    uri = chunks[i].web.uri
                    citation_links.append(f"[{i + 1}]({uri})")
            citation_string = ", ".join(citation_links)
            text = text[:end_index] + " " + citation_string + text[end_index:]

    return text

def save_response_to_file(token_usage, prompt_text, response_text, folder_path="responses"):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    existing_files = os.listdir(folder_path)
    file_count = len(existing_files)
    new_file_name = f"{file_count + 1}.md"
    new_file_path = os.path.join(folder_path, new_file_name)
    text = f"TokensUsage:\n{token_usage}\n\nPrompt:\n{prompt_text}\n\nResponse:\n{response_text}"
    with open(new_file_path, "w", encoding="utf-8") as file:
        file.write(text)
    print(f"Response saved to {new_file_path}")

if __name__ == "__main__":
    print("Start main")
    asyncio.run(main("", SCRIPT))