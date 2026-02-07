import asyncio
import os
import json
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

from utils.profiler import trace, profiler

# 디버그 설정
DEBUG_MODE = True
DEBUG_DIR = Path("debug")

# --- Configuration ---
USE_JSON_OUTPUT = True
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.1"
FRIENDLI_BASE_URL = "https://api.friendli.ai/serverless/v1"

# 사용 가능한 모델 목록
AVAILABLE_MODELS = {
    "exaone": "LGAI-EXAONE/K-EXAONE-236B-A23B",
    "qwen": "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "deepseek": "deepseek-ai/DeepSeek-V3.1",
}

# temperature 파라미터를 지원하지 않는 모델
NO_TEMPERATURE_MODELS = [
    "LGAI-EXAONE/K-EXAONE-236B-A23B",
]

# Rate limit 재시도 설정
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
# ---------------------


def save_debug_log(model_name: str, ad_name: str, messages: list, response_content: str, error: str = None, elapsed: float = 0):
    """각 요청/응답을 markdown 파일로 저장"""
    if not DEBUG_MODE:
        return
    
    DEBUG_DIR.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_short = model_name.split("/")[-1] if "/" in model_name else model_name
    filename = f"{timestamp}_{model_short}_{ad_name[:10]}.md"
    filepath = DEBUG_DIR / filename
    
    content = f"""# Debug Log: {model_name}

## Meta
- **Timestamp**: {datetime.now().isoformat()}
- **Model**: `{model_name}`
- **Ad Name**: {ad_name}
- **Elapsed**: {elapsed:.2f}s
- **Status**: {'❌ ERROR' if error else '✅ SUCCESS'}

## Request (Messages)

### System Prompt
```
{messages[0]['content'] if messages else 'N/A'}
```

### User Content
```
{messages[1]['content'] if len(messages) > 1 else 'N/A'}
```

## Response

"""
    
    if error:
        content += f"""### Error
```
{error}
```
"""
    else:
        content += f"""### Raw Response
```json
{response_content}
```
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"📝 Debug log saved: {filepath}")
    return filepath

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


@trace("Friendli Analysis")
async def main(prompt, script, model_name=DEFAULT_MODEL):
    """
    Friendli.ai Serverless API를 사용하여 광고 스크립트를 분석합니다.
    
    Args:
        prompt: 사용자 정의 프롬프트 (빈 문자열이면 기본 프롬프트 사용)
        script: 분석할 광고 스크립트
        model_name: 사용할 모델 (기본값: deepseek-ai/DeepSeek-V3.1)
                   - "exaone" 또는 "LGAI-EXAONE/K-EXAONE-236B-A23B"
                   - "qwen" 또는 "Qwen/Qwen3-235B-A22B-Instruct-2507"
                   - "deepseek" 또는 "deepseek-ai/DeepSeek-V3.1"
    """
    load_dotenv()
    
    # 1. API 키 확인
    api_key = os.environ.get("FRIEDNLIAI_API_KEY")
    if not api_key:
        return json.dumps({
            "status": "error",
            "message": "FRIEDNLIAI_API_KEY 환경 변수가 설정되지 않았습니다."
        }, ensure_ascii=False)
    
    # 2. 모델명 정규화 (별칭 지원)
    if model_name.lower() in AVAILABLE_MODELS:
        model_name = AVAILABLE_MODELS[model_name.lower()]
    
    # 3. OpenAI 호환 클라이언트 생성
    try:
        client = AsyncOpenAI(
            base_url=FRIENDLI_BASE_URL,
            api_key=api_key
        )
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Friendli 클라이언트 생성 실패: {str(e)}"
        }, ensure_ascii=False)

    # 4. 프롬프트 설정
    if USE_JSON_OUTPUT:
        target_prompt = PROMPT_6
        print(f"[Friendli:{model_name}] 모드: JSON 구조화 출력")
    else:
        target_prompt = PROMPT_5
        print(f"[Friendli:{model_name}] 모드: 일반 텍스트 출력")
    
    # 사용자 정의 프롬프트가 있으면 사용
    if prompt and prompt.strip():
        target_prompt = prompt

    full_user_content = f"[광고 스크립트]:\n{script}"
    
    # Qwen3 특수 처리: Thinking mode 비활성화
    if "qwen3" in model_name.lower():
        full_user_content = full_user_content + "\n\n/no_think"
    
    messages = [
        {"role": "system", "content": target_prompt},
        {"role": "user", "content": full_user_content}
    ]

    print(f"Friendli({model_name})에게 요청을 보내는 중...")
    start_time = time.perf_counter()

    # ad_name 추출 (벤치마크용)
    ad_name = script[:20].replace("\n", " ").strip()
    
    try:
        # 5. API 호출 (재시도 로직 포함)
        response = None
        last_error = None
        
        for attempt in range(MAX_RETRIES):
            try:
                # 모델에 따라 temperature 파라미터 제외
                create_params = {
                    "model": model_name,
                    "messages": messages,
                }
                
                # temperature를 지원하는 모델만 추가
                if model_name not in NO_TEMPERATURE_MODELS:
                    create_params["temperature"] = 0.1
                
                response = await client.chat.completions.create(**create_params)
                break  # 성공 시 루프 탈출
                
            except Exception as api_error:
                last_error = str(api_error)
                error_msg = str(api_error).lower()
                
                # Rate limit 에러는 재시도
                if "rate limit" in error_msg or "429" in str(api_error):
                    print(f"⚠️ Rate limit hit, 재시도 {attempt + 1}/{MAX_RETRIES} ({RETRY_DELAY}s 대기)")
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))  # 점진적 대기
                    continue
                else:
                    # 다른 에러는 즉시 실패
                    raise api_error
        
        if response is None:
            raise Exception(f"Max retries exceeded: {last_error}")
        
        duration = time.perf_counter() - start_time
        profiler.log_manual(f"Friendli API ({model_name})", duration)

        content = response.choices[0].message.content
        print(f"✅ 분석 완료 ({duration:.2f}s)")

        # 6. JSON 파싱 시도
        if USE_JSON_OUTPUT:
            try:
                # JSON 블록 추출 시도 (```json ... ``` 형식 처리)
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                
                json_data = json.loads(content)
                result = json.dumps(json_data, ensure_ascii=False)
                
                # 디버그 로그 저장 (성공)
                save_debug_log(
                    model_name=model_name,
                    ad_name=ad_name,
                    messages=messages,
                    response_content=result,
                    elapsed=duration
                )
                
                return result
            except json.JSONDecodeError:
                print("JSON 파싱 실패, 원본 텍스트 반환")
                
                # 디버그 로그 저장 (파싱 실패)
                save_debug_log(
                    model_name=model_name,
                    ad_name=ad_name,
                    messages=messages,
                    response_content=content,
                    error="JSON 파싱 실패",
                    elapsed=duration
                )
                
                return json.dumps({
                    "reliability_level": "정보 부족",
                    "summary": "AI 응답 형식이 올바르지 않습니다.",
                    "issues": ["JSON 파싱 에러"],
                    "patent_check": None,
                    "evidence": [],
                    "consultation": f"원본 응답: {content[:200]}..."
                }, ensure_ascii=False)
        
        # 디버그 로그 저장 (일반 텍스트)
        save_debug_log(
            model_name=model_name,
            ad_name=ad_name,
            messages=messages,
            response_content=content,
            elapsed=duration
        )
        
        return content

    except Exception as e:
        elapsed = time.perf_counter() - start_time
        print(f"Friendli 분석 중 에러: {e}")
        
        # 디버그 로그 저장 (에러)
        save_debug_log(
            model_name=model_name,
            ad_name=ad_name,
            messages=messages,
            response_content="",
            error=str(e),
            elapsed=elapsed
        )
        
        return json.dumps({
            "status": "error",
            "message": str(e)
        }, ensure_ascii=False)


if __name__ == "__main__":
    # Test
    SCRIPT = "비문증 방치하면 실명된다. 이거 먹으면 낫는다. 특허 받았다."
    
    print("=== DeepSeek-V3.1 테스트 ===")
    result = asyncio.run(main("", SCRIPT, "deepseek"))
    print(result)
    
    # print("\n=== EXAONE 테스트 ===")
    # result = asyncio.run(main("", SCRIPT, "exaone"))
    # print(result)
