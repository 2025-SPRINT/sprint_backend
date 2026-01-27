import asyncio
import os
import json
import time
from datetime import datetime
from typing import Literal, List, Optional
from typing_extensions import TypedDict
from dotenv import load_dotenv
import ollama

from utils.profiler import trace, profiler

# --- Configuration ---
USE_JSON_OUTPUT = True
DEFAULT_MODEL = "exaone-deep:7.8b"
OLLAMA_HOST = "http://localhost:11434"
# ---------------------

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
    patent_check: Optional[PatentCheck]
    evidence: List[EvidenceItem]
    consultation: str

PROMPT_5 = """
# Role
당신은 공정하고 객관적인 '광고 신뢰성 분석가'입니다. 귀하의 목표는 제공된 광고 스크립트의 주장을 검증하여, 소비자가 올바른 판단을 내릴 수 있도록 사실에 입각한 분석 리포트를 제공하는 것입니다.

# Principles
1. **중립성 유지**: 광고가 무조건 거짓이라거나, 무조건 진실이라고 예단하지 마십시오. 오직 '검증된 증거'에 기반하여 판단하십시오.
2. **증거 기반 평가 (Logic based)**: 현재 외부 도구(검색, KIPRIS)를 사용할 수 **없습니다**. 오직 광고 스크립트의 **논리적 모순**과 **보편적 과학 상식**에 기반하여 분석하십시오.
3. **환각 방지**: 검색을 할 수 없으므로, 특허가 '존재한다'거나 '거짓이다'라고 확정적으로 말하지 마시오. 대신 "검증이 필요하다"고 표현하십시오.

# Process
1. **주장 식별**: 광고의 핵심 주장(효능, 특허 언급, 인증 등)을 파악합니다.
2. **논리적 검증**: 주장이 과학적으로 타당한지, 과장된 표현(예: "100% 완치", "즉각 효과")이 있는지 확인합니다.
3. **리포트 작성**: 분석 결과를 친절하고 명확한 어조로 작성합니다.

# Output Format
보고서는 디지털 정보 취약 계층도 이해하기 쉽도록 작성하십시오.

1. **종합 평가 등급**: [안전 / 주의 / 위험 / 정보 부족] 중 택 1.
2. **주요 검증 결과**: 광고의 주장과 이에 대한 논리적/과학적 반박.
3. **소비자 가이드**: 주의사항 및 조언.

# Context
이후 내용은 사용자가 시청한 유튜브 쇼츠 광고의 스크립트입니다. 위 지침을 준수하여 분석하십시오.
"""

PROMPT_6 = """
# Role
당신은 공정하고 객관적인 '광고 신뢰성 분석가'입니다. 귀하의 목표는 제공된 광고 스크립트의 주장을 검증하여, 소비자가 올바른 판단을 내릴 수 있도록 사실에 입각한 **간결한** 분석 리포트를 제공하는 것입니다.

# Principles
1. **중립성 유지**: 광고가 무조건 거짓이라거나, 무조건 진실이라고 예단하지 마십시오.
2. **도구 미사용**: 현재 인터넷 검색이나 특허 검색 도구를 사용할 수 **없습니다**. 오직 스크립트 내의 **논리적 허점**, **과학적 오류**, **과장된 표현**을 분석하는 데 집중하십시오.
3. **환각 방지**: 사실 관계를 확인할 수 없는 경우(예: 특정 특허 번호의 유효성), 거짓이라고 단정 짓지 말고 "확인이 필요함"으로 표기하십시오.
4. **간결성**: 출력은 최대한 간결하게 작성하십시오.

# Output Guidelines (JSON)
- `reliability_level`: "안전", "주의", "위험", "정보 부족" 중 하나 선택.
- `summary`: 핵심 문제점을 **한 문장**으로 요약. (최대 50자)
- `issues`: 핵심 문제점(논리적 오류, 과장 광고 등)만 **간단한 문구**로 나열.
- `patent_check`: 광고에 특허 관련 언급이 있으면 `status`를 "미확인"으로 하고, `details`에 "특허 검색 도구 미연동으로 확인 불가"라고 적으십시오. 언급이 없으면 `null`로 설정.
- `evidence`: 과학적 상식이나 논리적 추론을 근거로 제시. (예: "단백질은 경구 섭취 시 아미노산으로 분해되므로 피부로 직접 가지 않음")
- `consultation`: **1-2문장**으로 핵심 조언만 제공.

# Context
이후 내용은 사용자가 시청한 유튜브 쇼츠 광고의 스크립트입니다. 위 지침을 준수하여 분석하십시오.
"""

@trace("Ollama Analysis")
async def main(prompt, script, model_name=DEFAULT_MODEL):
    """
    Ollama를 사용하여 광고 스크립트를 분석합니다.
    """
    load_dotenv()
    
    # 1. Prepare Client
    try:
        client = ollama.AsyncClient(host=OLLAMA_HOST)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Ollama 클라이언트 연결 실패: {str(e)}"
        }, ensure_ascii=False)

    # 2. Prepare Tool/Prompt Configuration
    # Note: Ollama (Exaone) might not support complex tool calling perfectly yet.
    # We will prioritize text analysis relying on internal knowledge/logic for now.
    
    if USE_JSON_OUTPUT:
        target_prompt = PROMPT_6
        format_type = 'json'
        print(f"[{model_name}] 모드: JSON 구조화 출력")
    else:
        target_prompt = PROMPT_5
        format_type = ''
        print(f"[{model_name}] 모드: 일반 텍스트 출력")

    full_prompt = f"{target_prompt}\n\n[광고 스크립트]:\n{script}"
    
    messages = [
        {'role': 'user', 'content': full_prompt}
    ]

    print(f"Ollama({model_name})에게 요청을 보내는 중...")
    start_time = time.perf_counter()

    try:
        # 3. Request Generation
        response = await client.chat(
            model=model_name,
            messages=messages,
            format=format_type, # Enforce JSON if requested
            options={
                'temperature': 0.1, # Low temperature for analytical tasks
            }
        )
        
        duration = time.perf_counter() - start_time
        profiler.log_manual(f"Ollama API ({model_name})", duration)

        content = response['message']['content']
        print(f"✅ 분석 완료 ({duration:.2f}s)")

        # 4. JSON Logic Check
        if USE_JSON_OUTPUT:
            try:
                # Ensure it's valid JSON
                json_data = json.loads(content)
                # Return strictly JSON string
                return json.dumps(json_data, ensure_ascii=False)
            except json.JSONDecodeError:
                print("JSON 파싱 실패, 원본 텍스트 반환")
                # Fallback: wrap in a basic JSON structure or return text
                return json.dumps({
                    "reliability_level": "정보 부족",
                    "summary": "AI 응답 형식이 올바르지 않습니다.",
                    "issues": ["JSON 파싱 에러"],
                    "patent_check": None,
                    "evidence": [],
                    "consultation": f"원본 응답: {content[:100]}..."
                }, ensure_ascii=False)
        
        return content

    except Exception as e:
        print(f"Ollama 분석 중 에러: {e}")
        return json.dumps({
            "status": "error",
            "message": str(e)
        }, ensure_ascii=False)

if __name__ == "__main__":
    # Test
    SCRIPT = "비문증 방치하면 실명된다. 이거 먹으면 낫는다. 특허 받았다."
    result = asyncio.run(main("", SCRIPT))
    print(result)
