"""요약·분석 탭 · build_summary_tab, on_summarize, on_request (김희진)"""
import logging
import gradio as gr
from hri.exception.errors import OutputFormatError
from hri.service.report_service import search_reports

logger = logging.getLogger(__name__)

# app.py의 요약, 분석 탭 id (report_view.SUUMARY_TAB_ID와 같아야 한다)
SUMMARY_TAB_ID = "summary"
NEED_REPORT_MESSAGE = "보고서를 선택하세요."
NEED_REQUEST_MESSAGE = "요청 내용을 입력하세요."
SUMMARY_FAIL_MESSAGE = "요약을 만들지 못했습니다."
SUMMARY_ERROR_MESSAGE = "요약 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
REQUEST_ERROR_MESSAGE = "요청을 처리하지 못했습니다."
EMPTY_ANSWER_MESSAGE = "요청을 처리했지만 표시할 답변이 없습니다."

# app.py, 다른 담당자가 컴포넌트를 꺼내 쓸때 쓰는 모음 (login_components 등과 같은 방식)
summary_components = {}

def _summarize_report(report_id: int):
    """summarize_report를 호출하는 시점에 불러와 실행한다.
    summary_service는 그래프(.env 설정 필요)를 불러오는 모듈이라, 화면 파일을 불러올 때 가 아니라
    실제로 요약할 때 가져온다 (화면 테스트가 .env 없이도 돌아가고, 테스트에서 이 함수만 바꿔 끼울 수 있다.)
    """
    from hri.service.summary_service import summarize_report
    
    return summarize_report(report_id)

def _run_agent(request: str, report_ids: list[int]):
    """
    run_agent_with_tools를 호출하는 시점에 불러와 실행한다
    (이유는 _summarize_report와 같다)."""
    from hri.router.tool_router import run_agent_with_tools

    return run_agent_with_tools(request, report_ids)

def _report_titles() -> dict[int, str]:
    """report_id -> 제목.
    목록을 못 가져와도 요약은 되게 빈 dict를 돌려준다."""
    try:
        return {r.report_id: r.title for r in search_reports()}
    except Exception:
        logger.exception("보고서 제목 조회 실패")
        return {}

def _page_label(start: int | None, end: int | None) -> str:
    """쪽 범위 문구.
    예) 'p.1-3', 'p.4', 쪽 정보가 없으면 ''"""
    if start is None:
        return ""
    if end is None or end == start:
        return f"p.{start}"
    return f"p.{start}-{end}"

def _summary_markdown(title: str, summary) -> str:
    """보고서 1건의 요약(ReportSummary)을 화면에 보여 줄 Markdown으로 바꾼다."""
    lines = [f"### {title}", "**3줄 요약**"]
    lines += [f"{i}. {line}" for i, line in enumerate(summary.three_lines, 1)]
    lines += ["", "**섹션별 요약**"]

    for s in summary.sections:
        pages = _page_label(s.start_page, s.end_page)
        heading = f"**{s.title}**" + (f"({pages})" if pages else "")
        lines.append(f"- {heading}: {s.summary}")

    return "\n".join(lines)

def build_summary_tab():
    """요약, 분석 탭 화면을 만든다.
    (gr.Blocks의 gr.Tabs 안에서 호출)
    맨 위에 보고서 선택(여러 개 가능)을 두고, 아래를 둘로 나눈다.
    - 왼쪽: 요약 버튼과 요약 결과(3줄 요약, 섹션별 요약)
    - 오른쪽: 자연어 요청 입려칸, 요청 실행 버튼과 분석 결과
    탭은 로그인 전에는 숨겨 둔 채(visible=False) 만들고, 로그인하면 on_login이 보이게 한다.
    이벤트 연결은 gr.State가 필요해서 build_app()이 connect_summary_events(state)로 한다.
    
    반환: gr.Tab (컴포넌트는 summary_components로 꺼내 쓴다)
    """
    with gr.Tab("요약, 분석", id=SUMMARY_TAB_ID, visible=False) as tab:
        report_dropdown = gr.Dropdown(label="보고서 선택 (여러 개 가능)", choices=[], multiselect=True)
        with gr.Row():
            with gr.Column(scale=1):
                summarize_btn = gr.Button("요약하기", variant="primary")
                summary_result = gr.Markdown()

            with gr.Column(scale=1):
                request = gr.Textbox(label="요청", placeholder="예) 선택한 보고서를 검증한 뒤 병합해 줘", lines=2)
                request_btn = gr.Button("요청 실행")
                request_result = gr.Markdown()

    summary_components.update(
        tab=tab,
        report_dropdown=report_dropdown,
        summarize_btn=summarize_btn,
        summary_result=summary_result,
        request=request,
        request_btn=request_btn,
        request_result=request_result
    )
    return tab

def on_summarize(report_ids: list[int]) -> str:
    """요약하기 버튼: 선택한 보고서마다 summarize_report()를 호출해 Markdown으로 보여 준다.
    캐시가 있는 보고서는 LLM을 부르지 않고 바로 나온다.
    한 보고서가 실패해도(OutputFormatError 등) 그 보고서 자리에만 안내 문구를 넣고 나머지는 계속한다.

    입력: report_ids (선택한 보고서 번호 목록)
    출력: str (화면에 보여 줄 Markdown)
    """
    if not report_ids:
        return NEED_REPORT_MESSAGE

    titles = _report_titles()
    parts = []

    for report_id in report_ids:
        title = titles.get(report_id, f"보고서 {report_id}")

        try:
            summary = _summarize_report(report_id)
        except OutputFormatError:
            parts.append(f"### {title}\n{SUMMARY_FAIL_MESSAGE}")
        except Exception:
            logger.exception("요약 실패: report_id=%s", report_id)
            parts.append(f"### {title}\n{SUMMARY_ERROR_MESSAGE}")
        else:
            parts.append(_summary_markdown(title, summary))
    return "\n\n---\n\n".join(parts)

def on_request(request: str, report_ids: list[int]) -> str:
    """요청 실행 버튼: 자연어 요청을 run_agent_with_tools()에 보내고 결과와 실행한 도구 이름을 보여 준다.
    보고서를 고르지 않아도 실행한다 (ECOS 조회처럼 보고서가 필요 없는 도구가 있고, 보고서가 필요한 도구는 도구 쪽에서 안내한다).
    run_agent_with_tools()가 (답변, 도구 이름 목록)을 돌려주면 도구 이름도 함께 보여 주고, 답변 문자열만 돌려주면 답변만 보여 준다.
    
    입력: request (자연어 요청), report_ids (선택한 보고서 번호 목록, 비어 있어도 됨)
    출력: str (화면에 보여 줄 Markdown)
    """
    request = (request or "").strip()
    if not request:
        return NEED_REQUEST_MESSAGE

    try:
        result = _run_agent(request, list(report_ids or []))
    except Exception:
        logger.exception("요청 실행 실패: %s", request)
        return REQUEST_ERROR_MESSAGE

    answer, tool_names = result if isinstance(result, tuple) else (result, [])
    answer = (answer or "").strip() or EMPTY_ANSWER_MESSAGE

    if not tool_names:
        return answer
    tools = " → ".join(f"`{name}`" for name in tool_names)

    return f"{answer}\n\n**실행한 도구**: {tools}"