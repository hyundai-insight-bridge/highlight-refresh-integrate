"""보고서 업로드 흐름 · build_ingest_graph, route_after_validate, load_text_node, extract_tables_node, process_charts_node, split_node, summarize_tables_node, persist_node (엄정현)

[뼈대 단계 · 3.8.8] 노드 연결만 명세대로 해 두고, 노드는 아무 값도 바꾸지 않는 가짜({} 반환)다.
노드 내용은 3.8.2(추출 노드)·3.8.3(분할·요약·저장 노드)에서 채운다.

흐름 (LangGraph 워크플로우 명세서 build_ingest_graph 행)
	START → validate → route_after_validate
		├─ 실패(state['error']) → END
		└─ 통과 → [load_text ∥ extract_tables ∥ extract_charts] (같은 단계에서 병렬 실행)
	extract_charts → process_charts
	[load_text, extract_tables, process_charts] 세 갈래가 모두 끝나면 → split → summarize_tables → persist → END
compile은 registry.get_ingest_graph()가 한 번만 한다.
"""

from langgraph.graph import END, START, StateGraph

from hri.domain.schemas import IngestState

# 검증을 통과하면 동시에 시작하는 추출 노드 3개
PARALLEL_EXTRACT = ["load_text", "extract_tables", "extract_charts"]


def _skeleton_node(state: IngestState) -> dict:
	"""뼈대용 가짜 노드: state를 바꾸지 않는다. 명세서에 함수 이름이 없는 노드(validate·extract_charts)도 이것을 쓴다."""
	return {}


def load_text_node(state: IngestState) -> dict:
	"""[뼈대] 3.8.2에서 구현: load_pdf → clean_text → find_body_start → {'pages', 'meta', 'warnings'}."""
	return {}


def extract_tables_node(state: IngestState) -> dict:
	"""[뼈대] 3.8.2에서 구현: extract_tables → validate_table → split_big_table → table_to_markdown → {'tables', 'warnings'}."""
	return {}


def process_charts_node(state: IngestState) -> dict:
	"""[뼈대] 3.8.2에서 구현: state['charts']마다 ocr_chart → chart_to_table … → {'tables', 'warnings'}."""
	return {}


def split_node(state: IngestState) -> dict:
	"""[뼈대] 3.8.3에서 구현: split_sections → split_text → {'sections', 'chunks'}."""
	return {}


def summarize_tables_node(state: IngestState) -> dict:
	"""[뼈대] 3.8.3에서 구현: summarize_tables → {'summarized_tables', 'chunks'}."""
	return {}


def persist_node(state: IngestState) -> dict:
	"""[뼈대] 3.8.3에서 구현: 한 트랜잭션으로 insert_report … add_chunks → commit (실패 시 rollback) → {'report_id', 'counts'}."""
	return {}


def route_after_validate(state: IngestState) -> list[str] | str:
	"""validate 노드 다음 갈 곳을 고른다.

	state['error']가 있으면(검증 실패) END를 돌려줘 끝내고,
	없으면 추출 노드 3개 이름 리스트를 돌려줘 같은 단계(superstep)에서 병렬 실행한다.
	"""
	if state.get("error"):
		return END
	return PARALLEL_EXTRACT


def build_ingest_graph() -> StateGraph:
	"""업로드 그래프를 노드·엣지까지 연결해 돌려준다 (compile 전 StateGraph)."""
	graph = StateGraph(IngestState)

	# 노드 8개
	graph.add_node("validate", _skeleton_node)
	graph.add_node("load_text", load_text_node)
	graph.add_node("extract_tables", extract_tables_node)
	graph.add_node("extract_charts", _skeleton_node)
	graph.add_node("process_charts", process_charts_node)
	graph.add_node("split", split_node)
	graph.add_node("summarize_tables", summarize_tables_node)
	graph.add_node("persist", persist_node)

	# 검증 → (실패면 END) / (통과면 추출 3개 병렬)
	graph.add_edge(START, "validate")
	graph.add_conditional_edges("validate", route_after_validate, [*PARALLEL_EXTRACT, END])

	# 차트는 잘라낸 뒤 표로 바꾸는 단계를 한 번 더 거친다
	graph.add_edge("extract_charts", "process_charts")

	# 세 갈래가 모두 끝나야 split 실행 (리스트로 묶은 엣지 = 모두 기다림)
	graph.add_edge(["load_text", "extract_tables", "process_charts"], "split")
	graph.add_edge("split", "summarize_tables")
	graph.add_edge("summarize_tables", "persist")
	graph.add_edge("persist", END)
	return graph
