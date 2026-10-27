"""보고서 업로드 흐름 · build_ingest_graph, validate_node, route_after_validate, load_text_node, extract_tables_node, process_charts_node, split_node, summarize_tables_node, persist_node (엄정현)

[3.8.1] 그래프 구성(build_ingest_graph)·검증 노드(validate_node)·검증 분기(route_after_validate)를 명세대로 채웠다.
나머지 노드는 아직 가짜({} 반환)다. 3.8.2(추출 노드)·3.8.3(분할·요약·저장 노드)에서 채운다.

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

# TODO(확인 필요): validate_pdf()가 ok=False인데 reason을 비워 돌려줄 때 화면에 보여 줄 문구.
#   명세서에는 'reason을 state['error']에 기록'만 있고, reason이 없을 때의 문구는 정해져 있지 않다.
#   지금 validate_pdf()는 실패할 때 항상 reason을 채우므로 대비용이다. 문구가 정해지면 이 값만 바꾼다.
VALIDATE_FAILED_REASON = "PDF 파일을 확인할 수 없습니다"


def _skeleton_node(state: IngestState) -> dict:
	"""뼈대용 가짜 노드: state를 바꾸지 않는다. 명세서에 함수 이름이 없는 extract_charts 노드가 쓴다 (3.8.2에서 교체)."""
	return {}


def validate_node(state: IngestState) -> dict:
	"""업로드한 PDF를 validate_pdf()로 검사한다 (확장자·용량·열림·진짜 PDF·암호·쪽 수).

	- 실패(ok=False): {'error': reason} → route_after_validate가 END로 보내 그래프를 끝낸다.
	- 통과(ok=True): {'error': None} (IngestState.error는 '정상이면 None')
	  빈 dict 대신 error=None을 돌려주면 stream(stream_mode='updates')에서 {'validate': {'error': None}}으로 와서
	  upload_report()가 검증 결과를 None이 아닌 dict로 받을 수 있다.

	validate_pdf는 함수 안에서 import한다: document_service가 hri.graph.registry를 import하므로
	파일 맨 위에서 import하면 graph ↔ service 순환 import가 생긴다.
	"""
	from hri.service.document_service import validate_pdf

	result = validate_pdf(state["file_path"])
	if not result.ok:
		return {"error": result.reason or VALIDATE_FAILED_REASON}
	return {"error": None}


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
	graph.add_node("validate", validate_node)
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
