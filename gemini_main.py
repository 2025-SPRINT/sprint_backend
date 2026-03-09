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

# =====================================================
# Global Configuration
# =====================================================
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_TEMPERATURE = 0.1

# =====================================================
# Debug Logger
# =====================================================

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
                
                if step['content']:
                    report.append(f"**Thought/Draft**:\n\n{step['content']}\n")
                
                if step['function_calls']:
                    report.append("#### 🛠️ Tool Usage (Function Calls)")
                    for fc in step['function_calls']:
                        args_json = json.dumps(fc.args, indent=2, ensure_ascii=False)
                        report.append(f"- **Tool**: `{fc.name}`")
                        report.append(f"- **Arguments**:\n```json\n  {args_json}\n```")
                report.append("---")

            elif role == "tool":
                report.append(f"### 📥 Tool Result (`{step['tool_name']}`) *[{time}]*")
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

# =====================================================
# Prompts
# =====================================================

PROMPT_STEP_1 = """
# Role
당신은 사실 확인 전문 연구원입니다. 사용자가 제공하는 광고 스크립트를 보고, 일반적인 의학적 합의, 제품의 식약처 인증 여부, 성분의 효능 등 사실 관계를 확인해야 합니다.

# Task
1. 제공된 광고 스크립트에서 검증이 필요한 핵심 내용(효능, 성분, 주의사항 등 일반적 청구 항목)을 추출하세요.
2. 당신에게 제공된 "Google Search" 도구를 사용하여 해당 내용을 확인하고 요약하세요. (특허 관련 내용은 이 단계에서 깊게 파고들지 않아도 됩니다.)
3. 당신이 찾아낸 사실(Fact)들을 리스트 형태로 정리하여 반환하세요.
"""

PROMPT_STEP_2 = """
# Role
당신은 특허 전문 조사관입니다. 사용자가 제공하는 광고 스크립트를 읽고, 광고 내에서 '특허', '출원', '등록' 등 특허와 관련된 주장이 있는지 파악해야 합니다.

# Task
1. 만약 광고에서 특허 관련 언급이 없다면 "해당 없음"이라고 답변을 종료하세요.
2. 특허 관련 언급이 있다면, 제공된 KIPRIS MCP 도구를 활용하여 해당 특허가 실제로 한국특허청에 등록되어 있는지 검색하세요.
3. KIPRIS 검색 시, 광고에 언급된 성분명, 기술명 등을 추출하여 전문적인 키워드로 바꾸어 검색해야 합니다. (예: 인삼 섭취 -> 인삼 추출물 조성물)
4. 만약 검색 결과가 있다면 해당 특허의 출원인, 번호, 발명 명칭, 내용 등과 광고의 주장이 일치하는지 요약하여 반환하세요.
5. 없다면 "특허 존재 미확인 또는 허위"라는 결론을 기록하세요.
"""

PROMPT_FINAL = """
# Role
당신은 대한민국 '표시·광고에 관한 법률' 및 '식약처 광고 심의 가이드라인'을 준수하는 공정하고 객관적인 '광고 신뢰성 분석가'입니다. 귀하의 목표는 제공된 광고 스크립트와 **사전에 검증된 두 가지 리포트(일반 팩트체크, 특허 검증체크)**를 바탕으로, 소비자가 올바른 판단을 내릴 수 있도록 사실에 입각한 **간결한 JSON 분석 리포트**를 반환하는 것입니다.

# Principles
1. **중립성 유지**: 아래 제공될 'Step 1(일반 팩트) / Step 2(특허 팩트)' 내용을 전적으로 신뢰하고 이를 근거로 평가하십시오.
2. **간결성 (Brevity)**: 프론트엔드에서 표시하기 용이하도록 불필요한 수식어나 반복을 피하십시오.
3. 점수 산정(최대 100점 시작, 위반 시 차감 또는 감점 합산) 등을 통해 객관적 등급을 결정하십시오.

# Scoring Criteria (결과 매핑 및 감점)
1. 사회공학적 조작 및 심리 분석 (40점) - 비현실적 이득(15점), 동질성 호소(15점), 의구심 차단(10점)
2. 압박형 다크패턴 분석 (30점) - 허위 시간 제한(15점), 허위 재고/수요(15점)
3. 사회적 증거 조작 및 권위 도용 (20점) - 조작된 승인(10점), 과도한 지인 사례(10점)
4. 언어적 결함 및 정보 은폐 (10점) - 비문(5점), 정보 은폐(5점)

# Output Guidelines (JSON 형태 준수)
1. `reliability_level`: "안전", "주의", "위험", "정보 부족" 중 하나 (0~35:안전 / 36~60:주의 / 61~100:위험)
2. `summary`: 검증 결과를 바탕으로 **한 문장**으로 요약. (최대 50자 권장)
3. `issues`: 광고의 문제점을 소비자가 즉각 인지하도록 **[수법: 구체적 사유]** 형식으로 작성. (항목당 20자 내외)
4. `patent_check`: 제공받은 Step 2 검증 자료에 특허 관련 내용이 있을 경우에만 작성. 없으면 반드시 `null` 처리.
5. `evidence`: Step 1 및 Step 2에서 확인된 핵심 근거 및 팩트 요약. **Step 1(구글 검색 그라운딩) 결과에 포함된 출처 링크([숫자](URL) 형태)를 찾아내어 `url` 항목에 반드시 원본 URL 문자열로 포함**하십시오.
6. `consultation`: **1-2문장** 핵심 조언.
7. `risk_score` : 평가된 의심 최종 성적 계산값.

이후 제공되는 문맥을 읽고 지침에 따라 분석해 주세요.
"""

# =====================================================
# JSON Schema
# =====================================================

class PatentCheck(TypedDict):
    status: Literal["존재", "미확인", "허위", "해당 없음"]
    details: str
    patent_number: Optional[str]

class EvidenceItem(TypedDict):
    source: str
    url: Optional[str]
    fact: str

class ScoreDetail(TypedDict):
    domain: str
    score: int
    violations: List[str]

class AdAnalysisResult(TypedDict):
    reliability_level: Literal["안전", "주의", "위험", "정보 부족"]
    risk_score: str
    score_breakdown: List[ScoreDetail]
    summary: str
    issues: List[str]
    patent_check: Optional[PatentCheck]
    evidence: List[EvidenceItem]
    consultation: str

# =====================================================
# Utility Functions
# =====================================================

def add_citations(response):
    """Gemini 응답에서 grounding citation 링크를 텍스트에 삽입"""
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
    """분석 결과를 파일로 저장"""
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


def _safe_get_text(response):
    """Gemini 응답에서 텍스트를 안전하게 추출"""
    if response.candidates[0].content.parts and any(p.text for p in response.candidates[0].content.parts):
        return response.text
    return None


def _accumulate_usage(total_usage, response_usage):
    """토큰 사용량 누적"""
    if response_usage:
        total_usage.prompt_token_count += response_usage.prompt_token_count
        total_usage.candidates_token_count += response_usage.candidates_token_count
        total_usage.total_token_count += response_usage.total_token_count

# =====================================================
# Pipeline Step Functions
# =====================================================

@trace("Step 1: Google Fact Check")
async def _step1_fact_check(client, script_text, logger, total_usage):
    """Google 검색 그라운딩으로 광고 주장 팩트체크 (자막만 전달)"""
    print("파이프라인 Step 1: 구글 검색 그라운딩 (팩트체크)")
    
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=GEMINI_TEMPERATURE
    )
    
    prompt = f"{PROMPT_STEP_1}\n\n[광고 스크립트]:\n{script_text}"
    logger.log_api_call("user", f"[STEP 1: Google Search]\n{prompt}")
    
    start = time.perf_counter()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=config
    )
    profiler.log_manual("Gemini API: Step 1 (Search)", time.perf_counter() - start)
    
    result_with_citations = add_citations(response)
    logger.log_api_call("model", result_with_citations)
    _accumulate_usage(total_usage, response.usage_metadata)
    
    return result_with_citations


@trace("Step 2: KIPRIS Patent Check")
async def _step2_patent_check(client, script_text, logger, total_usage):
    """KIPRIS MCP로 특허 검증 (자막만 전달)"""
    print("파이프라인 Step 2: KIPRIS 특허 검증")
    
    connector, kipris_tools = await get_singleton_connector()
    
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=kipris_tools)],
        temperature=GEMINI_TEMPERATURE
    )
    
    prompt = f"{PROMPT_STEP_2}\n\n[광고 스크립트]:\n{script_text}"
    logger.log_api_call("user", f"[STEP 2: KIPRIS]\n{prompt}")
    history = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    
    start = time.perf_counter()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=history,
        config=config
    )
    profiler.log_manual("Gemini API: Step 2 (MCP Initiation)", time.perf_counter() - start)
    _accumulate_usage(total_usage, response.usage_metadata)
    
    res_text = _safe_get_text(response) or "[Tool Call Only]"
    logger.log_api_call("model", f"[STEP 2 Init]\n{res_text}",
                        function_calls=[p.function_call for p in response.candidates[0].content.parts if p.function_call])

    # MCP Tool Execution Loop
    max_turns = 4
    turn_count = 0
    current_response = response
    called_tools = set()
    
    while (turn_count < max_turns 
           and current_response.candidates[0].content.parts 
           and any(p.function_call for p in current_response.candidates[0].content.parts)):
        turn_count += 1
        history.append(current_response.candidates[0].content)
        
        tool_parts = []
        for part in current_response.candidates[0].content.parts:
            if not part.function_call:
                continue
                
            name = part.function_call.name
            args = part.function_call.args
            
            if name == "google_search":
                continue
                
            # 중복 호출 방지
            call_sig = f"{name}-{args}"
            if call_sig in called_tools:
                print(f"로그: 중복 도구 호출 감지, 루프 종료 - {call_sig}")
                break
            called_tools.add(call_sig)
                
            print(f"로그: MCP 도구 호출 중 - {name}({args})")
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
                    
        if not tool_parts:
            break
            
        history.append(types.Content(role="tool", parts=tool_parts))
        start = time.perf_counter()
        current_response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=history,
            config=config
        )
        profiler.log_manual(f"Gemini API: Step 2 Turn {turn_count}", time.perf_counter() - start)
        _accumulate_usage(total_usage, current_response.usage_metadata)
            
        inner_text = _safe_get_text(current_response) or "[Tool Call Only]"
        logger.log_api_call("model", inner_text,
                            function_calls=[p.function_call for p in current_response.candidates[0].content.parts if p.function_call])

    return _safe_get_text(current_response) or "특허 검증 결과 획득 불가"


@trace("Step 3: Final Synthesis")
async def _step3_synthesize(client, script_text, site_details, comments_data, 
                             discovery_data, step1_result, step2_result, logger, total_usage):
    """모든 정보를 통합하여 최종 JSON 리포트 생성"""
    print("파이프라인 Step 3: 최종 JSON 리포트 생성")
    
    discovery = discovery_data if discovery_data else {}
    
    final_prompt = f"""{PROMPT_FINAL}

=== 광고 스크립트 ===
{script_text}

=== 부가 정보 ===
[사용자 댓글 및 반응]:
{comments_data or "댓글 정보 없음"}

[웹사이트 분석 상세 내용]:
{json.dumps(site_details, indent=2, ensure_ascii=False) if site_details else "사이트 분석 정보 없음"}

[추출된 브랜드/상품 정보]:
- 브랜드: {discovery.get('brand', '미확인')}
- 법인명: {discovery.get('Corporate Name', '미확인')}
- 상품명: {discovery.get('product_name', '미확인')}

=== 단계별 검증 결과 ===
[Step 1: 구글 검색 그라운딩 (팩트체크) 결과]:
{step1_result}

[Step 2: KIPRIS 특허 검증 결과]:
{step2_result}
"""

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AdAnalysisResult,
        temperature=GEMINI_TEMPERATURE
    )

    logger.log_api_call("user", f"[STEP 3: Final Integration]\n{final_prompt}")
    
    start = time.perf_counter()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=final_prompt,
        config=config
    )
    profiler.log_manual("Gemini API: Final Step (Synthesize)", time.perf_counter() - start)
    _accumulate_usage(total_usage, response.usage_metadata)

    final_text = response.text
    logger.log_api_call("model", final_text)

    # 결과 출력
    print("\n[최종 분석 결과]\n")
    try:
        json_data = json.loads(final_text)
        print(json.dumps(json_data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print("JSON 파싱 실패:")
        print(final_text)
    print("\n" + "=" * 50 + "\n")

    return final_text

# =====================================================
# Public Entry Point
# =====================================================

@trace("Gemini Analysis (Full)")
async def analyze_ad(script_text, site_details=None, comments_data=None, discovery_data=None):
    """광고 분석 파이프라인 진입점.
    
    Args:
        script_text: 유튜브 자막 텍스트 (순수 스크립트)
        site_details: 웹사이트 상세 분석 결과 (step2_deep_verification)
        comments_data: 댓글 문자열
        discovery_data: 브랜드/법인/상품 정보 (step1_video_discovery)
    
    Returns:
        str: JSON 형태의 분석 리포트 문자열
    """
    load_dotenv()
    client = genai.Client(api_key=os.getenv("api_key_grounding"))
    
    logger = GeminiDebugLogger()
    total_usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=0,
        candidates_token_count=0,
        total_token_count=0
    )

    # Step 1 & 2: 자막만 전달하여 팩트체크 / 특허검증 (병렬 실행)
    step1_result, step2_result = await asyncio.gather(
        _step1_fact_check(client, script_text, logger, total_usage),
        _step2_patent_check(client, script_text, logger, total_usage),
    )

    # Step 3: 모든 정보를 통합하여 최종 리포트 생성
    final_text = await _step3_synthesize(
        client, script_text, site_details, comments_data, discovery_data,
        step1_result, step2_result, logger, total_usage
    )

    # 로그 저장
    logger.set_usage(total_usage)
    debug_path = logger.save()
    print(f"\n[Debug] 상세 API 호출 흐름이 저장되었습니다: {debug_path}")

    save_response_to_file(total_usage, PROMPT_FINAL, final_text)

    return final_text