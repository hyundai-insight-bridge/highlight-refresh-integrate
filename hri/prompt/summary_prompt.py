"""요약·검증·병합 · summarize_sections, summarize_three_lines, verify_and_expand, merge_reports (김희진)"""
from hri.domain.schemas import Section, SectionSummary, ThreeLineSummary
from hri.exception.errors import OutputFormatError
from hri.llm.llm_client import get_chat_model

MAX_ATTEMPTS = 2 # 형식이 어긋났을 때 시도하는 횟수 (첫 1번 + 재시도 1번)
MAX_SECTION_CHARS = 8000 # 섹션 원문을 LLM에 보내는 최대 글자 수
SECTION_MAX_TOKENS = 600
THREE_LINES_MAX_TOKENS = 800
LINE_MAX_CHARS = 60 # ThreeLineSummary.lines 설명의 "각 줄 60자 이내"와 같은 값

SECTION_SYSTEM_PROMPT = (
    "당신은 경제 보고서를 요약하는 애널리스트입니다.\n"
    "주어진 섹션 1개의 핵심 내용을 2~3문장으로 요약하세요.\n"
    "- 수치와 단위는 원문 그대로 씁니다.\n"
    "- 원문에 없는 내용은 쓰지 않습니다.\n"
    "- title에는 섹션 제목을 그대로 씁니다."
)

THREE_LINES_SYSTEM_PROMPT = (
    "당신은 경제 보고서를 요약하는 애널리스트입니다.\n"
    "아래는 한 보고서의 섹션별 요약입니다. 이를 바탕으로 보고서 전체를 3줄로 요약하세요.\n"
    "- 1줄: 핵심 주장\n"
    "- 2줄: 그 주장을 뒷받침하는 근거 수치\n"
    "- 3줄: 시사점\n"
    f"- 각 줄은 {LINE_MAX_CHARS}자 이내의 한 문장으로 씁니다.\n"
    "- 수치와 단위는 요약에 있는 그대로 쓰고, 요약에 없는 내용은 만들지 않습니다.\n"
    "- 줄 앞에 번호나 기호를 붙이지 않습니다."
)

def _invoke_with_retry(model, messages, is_valid):
    """구조화 출력 호출을 MAX_ATTEMPTS번까지 시도해 검증을 통과한 결과를 돌려준다.
    모두 실패하면 None."""
    for _ in range(MAX_ATTEMPTS):
        try:
            result = model.invoke(messages)
        except Exception:
            continue
        if result is not None and is_valid(result):
            return result
    return None

def summarize_sections(sections: list[Section]) -> list[SectionSummary]:
    """
    섹션마다 LLM으로 2~3문장 요약(SectionSummary)을 만들어 입력 순서대로 돌려준다.
    summary_graph의 summarize_section 노드가 섹션 1개씩 [section]으로 호출한다. 빈 목록이면 [].
    title은 원문 제목으로 덮어쓰고, section_id(=section_no)와 start_page, end_page는 Section에서 채운다.
    원문이 MAX_SECTION_CHARS를 넘으면 앞부분만 보낸다.
    형식이 어긋나면 MAX_ATTEMPTS번까지 시도하고, 계속 실패하면 OutputFormatError를 낸다.
    """
    if not sections:
        return []

    model = get_chat_model(temperature=0, max_tokens=SECTION_MAX_TOKENS).with_structured_output(SectionSummary)
    results: list[SectionSummary] = []

    for section in sections:
        messages = [
            ("system", SECTION_SYSTEM_PROMPT),
            ("human", f"섹션 제목: {section.title}\n\n본문:\n{section.text[:MAX_SECTION_CHARS]}"),
        ]
        summary = _invoke_with_retry(model, messages, lambda x: bool(x.summary.strip()))

        if summary is None:
            raise OutputFormatError(f"섹션 요약 형식이 올바르지 않습니다. (section_no={section.section_no})")
        results.append(summary.model_copy(update={
            "title": section.title,
            "summary": summary.summary.strip(),
            "section_id": section.section_no,
            "start_page": section.start_page,
            "end_page": section.end_page,
        }))
    
    return results

def summarize_three_lines(section_summaries: list[SectionSummary]) -> ThreeLineSummary:
    """
    섹션별 요약을 모아 보고서 전체를 3줄(핵심 주장 / 근거 수치 / 시사점)로 요약한다.
    summary_graph의 three_lines 노드가 사용하며, 호출부는 결과의 lines를 쓴다.
    section_summaries는 start_page 순으로 정렬해서 넘긴다. 빈 목록이면 ValueError.
    형식이 어긋나면 MAX_ATTEMPTS번까지 시도하고, 계속 실패하면 OutputFormatError를 낸다.
    """
    if not section_summaries:
        raise ValueError("섹션 요약이 없어 3줄 요약을 만들 수 없습니다.")
    body = "\n\n".join(f"[{s.title}]\n{s.summary}" for s in section_summaries)
    messages = [
        ("system", THREE_LINES_SYSTEM_PROMPT),
        ("human", f"섹션별 요약:\n\n{body}"),
    ]
    model = get_chat_model(temperature=0, max_tokens=THREE_LINES_MAX_TOKENS).with_structured_output(ThreeLineSummary)
    result = _invoke_with_retry(model, messages, lambda x: all(line.strip() for line in x.lines))

    if result is None:
        raise OutputFormatError("3줄 요약 형식이 올바르지 않습니다.")
    return result.model_copy(update={"lines": [line.strip() for line in result.lines]})