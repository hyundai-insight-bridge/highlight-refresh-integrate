"""보고서 요약 흐름 · build_summary_graph, fan_out_sections (엄정현)

[뼈대 단계 · 3.8.8] 노드 연결만 명세대로 해 두고, 노드는 아무 값도 바꾸지 않는 가짜({} 반환)다.
노드 내용은 3.8.6에서 채운다.

흐름 (LangGraph 워크플로우 명세서 build_summary_graph 행)
	START → load_cache → (reports.summary_json이 있으면 END)
	      → load_sections → fan_out_sections
		├─ state['error'](섹션 0개) → END
		└─ 섹션마다 Send('summarize_section', {'section': s}) → summarize_section (섹션별 병렬)
	→ three_lines → save → END
compile은 registry.get_summary_graph()가 한 번만 한다.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from hri.domain.schemas import SummaryState


def _skeleton_node(state: SummaryState) -> dict:
	"""뼈대용 가짜 노드: state를 바꾸지 않는다 (load_cache·load_sections·summarize_section·three_lines·save)."""
	return {}


def route_after_cache(state: SummaryState) -> str:
	"""[뼈대 · 확인 필요] load_cache 다음 갈 곳. 캐시가 있으면 END, 없으면 load_sections.

	명세서에는 'reports.summary_json이 있으면 END'만 있고 함수 이름과,
	캐시가 있는지를 state의 어느 키로 알리는지가 없다 (SummaryState에 캐시용 키가 없음).
	뼈대에서는 항상 load_sections로 보낸다. 3.8.6에서 정한다.
	"""
	return "load_sections"


def fan_out_sections(state: SummaryState) -> list[Send] | str:
	"""섹션마다 summarize_section 노드를 하나씩 보내 병렬로 요약한다 (map).

	- state['error']가 있으면(섹션 0개 오류, load_sections 노드가 설정) END를 돌려준다.
	  라우팅 함수는 state를 바꿀 수 없으므로 오류 기록은 load_sections 노드가 한다.
	- 아니면 state['sections']마다 Send('summarize_section', {'section': s})를 만든다.
	- 각 summarize_section이 돌려준 section_summaries는 operator.add 리듀서로 모인다 (reduce).
	"""
	if state.get("error"):
		return END
	return [Send("summarize_section", {"section": s}) for s in state.get("sections", [])]


def build_summary_graph() -> StateGraph:
	"""요약 그래프를 노드·엣지까지 연결해 돌려준다 (compile 전 StateGraph)."""
	graph = StateGraph(SummaryState)

	graph.add_node("load_cache", _skeleton_node)
	graph.add_node("load_sections", _skeleton_node)
	graph.add_node("summarize_section", _skeleton_node)
	graph.add_node("three_lines", _skeleton_node)
	graph.add_node("save", _skeleton_node)

	graph.add_edge(START, "load_cache")
	graph.add_conditional_edges("load_cache", route_after_cache, ["load_sections", END])
	graph.add_conditional_edges("load_sections", fan_out_sections, ["summarize_section", END])
	# Send로 나뉜 summarize_section이 모두 끝나면 three_lines가 한 번 실행된다
	graph.add_edge("summarize_section", "three_lines")
	graph.add_edge("three_lines", "save")
	graph.add_edge("save", END)
	return graph
