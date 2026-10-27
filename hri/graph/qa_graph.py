"""질의응답 흐름 · build_qa_graph, route_question, route_after_grade, generate_node, no_answer_node, error_reply_node, save_log_node (엄정현)

[뼈대 단계 · 3.8.8] 노드 연결만 명세대로 해 두고, 노드는 아무 값도 바꾸지 않는 가짜({} 반환)다.
노드·분류 내용은 3.8.4(그래프 구성·분기)·3.8.5(답변·기록 노드)에서 채운다.

흐름 (LangGraph 워크플로우 명세서 build_qa_graph 행)
	START → validate → route_question
		├─ 'error'   → error_reply ─────────────────────────────┐
		├─ 'chat'    → chat ────────────────────────────────────┤
		└─ 'rewrite' → rewrite → retrieve → grade → route_after_grade
				├─ 'no_answer' → no_answer ─────────────────────┤
				└─ 'generate'  → generate → [sources ∥ suggest] ┴→ save_log → END
compile(checkpointer=get_checkpointer())은 registry.get_qa_graph()가 한 번만 한다.
"""

from typing import Literal

from langgraph.graph import END, START, StateGraph

from hri.domain.schemas import QAState


def _skeleton_node(state: QAState) -> dict:
	"""뼈대용 가짜 노드: state를 바꾸지 않는다. 명세서에 함수 이름이 없는 노드(validate·chat·rewrite·retrieve·grade·sources·suggest)도 이것을 쓴다."""
	return {}


def generate_node(state: QAState) -> dict:
	"""[뼈대] 3.8.5에서 구현: get_context_docs → format_docs → build_messages → LLM → {'answer', 'has_source': True, 'route': 'rag', ...}."""
	return {}


def no_answer_node(state: QAState) -> dict:
	"""[뼈대] 3.8.5에서 구현: LLM 없이 {'answer': '자료에 없습니다', 'has_source': False, 'route': 'no_answer', ...}."""
	return {}


def error_reply_node(state: QAState) -> dict:
	"""[뼈대] 3.8.5에서 구현: LLM 없이 state['error']를 answer로 → {'answer', 'has_source': False, 'route': 'error', ...}."""
	return {}


def save_log_node(state: QAState) -> dict:
	"""[뼈대] 3.8.5에서 구현: 응답 시간·원화 비용 계산 → save_qa_log → insert_usage(flow='qa') → {'log_id'}."""
	return {}


def route_question(state: QAState) -> Literal["chat", "rewrite", "error"]:
	"""validate 노드 다음 갈 곳을 고른다.

	- state['error']가 있으면(InvalidInputError) 'error' → error_reply 노드
	- [뼈대] 그 밖에는 모두 'rewrite'로 보낸다.
	  3.8.4에서 명세대로 채운다: GREETING_RE에 걸리면 'chat', extract_keywords() 결과가 있으면 'rewrite',
	  애매하면 get_chat_model(temperature=0).with_structured_output(RouteDecision)으로 분류.
	"""
	if state.get("error"):
		return "error"
	return "rewrite"


def route_after_grade(state: QAState) -> Literal["generate", "no_answer"]:
	"""grade 노드 다음 갈 곳: 근거가 있으면 'generate', 없으면 'no_answer'.

	[뼈대 · 확인 필요] 명세서는 'grade 노드(has_context)가 False면 no_answer'인데,
	grade 결과를 state의 어느 키에 적는지가 없다 (QAState에 has_context 키가 없음).
	has_context()는 '검색 결과 청크가 비었는지'만 보므로, 뼈대에서는 state['docs']가 비었는지로 같은 판단을 한다.
	"""
	if state.get("docs"):
		return "generate"
	return "no_answer"


def build_qa_graph() -> StateGraph:
	"""질의응답 그래프를 노드·엣지까지 연결해 돌려준다 (compile 전 StateGraph)."""
	graph = StateGraph(QAState)

	# 노드 11개
	graph.add_node("validate", _skeleton_node)
	graph.add_node("chat", _skeleton_node)
	graph.add_node("error_reply", error_reply_node)
	graph.add_node("rewrite", _skeleton_node)
	graph.add_node("retrieve", _skeleton_node)
	graph.add_node("grade", _skeleton_node)
	graph.add_node("no_answer", no_answer_node)
	graph.add_node("generate", generate_node)
	graph.add_node("sources", _skeleton_node)
	graph.add_node("suggest", _skeleton_node)
	graph.add_node("save_log", save_log_node)

	# 검증 → 질문 분류 (route_question의 반환값 → 갈 노드 이름)
	graph.add_edge(START, "validate")
	graph.add_conditional_edges(
		"validate",
		route_question,
		{"chat": "chat", "rewrite": "rewrite", "error": "error_reply"},
	)

	# 보고서 질문: 다시 쓰기 → 검색 → 근거 확인 → (답변 | 근거 없음)
	graph.add_edge("rewrite", "retrieve")
	graph.add_edge("retrieve", "grade")
	graph.add_conditional_edges(
		"grade",
		route_after_grade,
		{"generate": "generate", "no_answer": "no_answer"},
	)

	# 답변 뒤 출처·추천 질문을 동시에 만들고, 둘 다 끝나면 기록
	graph.add_edge("generate", "sources")
	graph.add_edge("generate", "suggest")
	graph.add_edge(["sources", "suggest"], "save_log")

	# 잡담·근거 없음·입력 오류도 기록 후 종료
	graph.add_edge("chat", "save_log")
	graph.add_edge("no_answer", "save_log")
	graph.add_edge("error_reply", "save_log")
	graph.add_edge("save_log", END)
	return graph
