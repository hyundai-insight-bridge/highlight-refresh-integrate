"""질의응답 흐름 · build_qa_graph, route_question, route_after_grade, generate_node, no_answer_node, error_reply_node, save_log_node (엄정현)

[3.8.4] 그래프 구성·분기(build_qa_graph·route_question·route_after_grade)와 체크포인터 연결을 명세대로 채웠다.
노드 내용은 아직 가짜({} 반환)다. generate·no_answer·error_reply·save_log는 3.8.5에서,
validate·chat·rewrite·retrieve·grade·sources·suggest는 각 함수(validate_question·chat_bot·rewrite_question·
hybrid_search·has_context·format_sources·suggest_questions)가 들어오면 연결한다.

흐름 (LangGraph 워크플로우 명세서 build_qa_graph 행)
	START → validate → route_question
		├─ 'error'   → error_reply ─────────────────────────────┐
		├─ 'chat'    → chat ────────────────────────────────────┤
		└─ 'rewrite' → rewrite → retrieve → grade → route_after_grade
				├─ 'no_answer' → no_answer ─────────────────────┤
				└─ 'generate'  → generate → [sources ∥ suggest] ┴→ save_log → END
compile(checkpointer=get_checkpointer())은 registry.get_qa_graph()가 한 번만 한다 (thread_id = session_id).
"""

import re
from typing import Literal

from langgraph.graph import END, START, StateGraph

from hri.domain.schemas import QAState, RouteDecision
from hri.prompt.rag_prompt import has_context

# 인사·감사·잡담 정규식 (명세서: '인사·감사·잡담 정규식(GREETING_RE)에 걸리면 chat')
# 질문 '전체'가 아래 표현(여러 개 이어져도 됨)과 문장부호로만 되어 있을 때만 'chat'이다.
# 문장 일부에만 들어 있으면 맞지 않는다 → '날씨가 경제에 미치는 영향은?', '음, 금리 전망은?'은 3단계로 간다.
_SEP = r"[\s,!.~?^ㅠㅜ]"  # 표현 사이·끝에 올 수 있는 공백·문장부호

# ① 인사·감사
_GREETING_WORDS = (
	r"안녕(?:하세요|하십니까|히\s*(?:계세요|가세요))?|반가워요?|반갑습니다|고마워요?|고맙습니다"
	r"|감사(?:합니다|해요|드립니다)?|수고(?:하세요|하셨습니다|했어요|하셨어요)?|잘\s*부탁(?:해요|드립니다)"
	r"|hi|hello|hey|thanks?|thank\s*you"
)
# ② 웃음·감탄만 있는 말: ㅋㅋ, ㅎㅎ, 음..., 오, 와
_REACTION_WORDS = r"[ㅋㅎ]+|음+|오+|와+"
# ③ 챗봇에 대한 질문: 너는 누구야, 뭐 할 수 있어, 이 서비스 기능
_BOT_WORDS = (
	r"(?:너는?|넌)?\s*누구(?:야|니|세요|예요|인가요)?"
	r"|(?:너는?|넌)?\s*(?:뭐|뭘|무엇을)\s*할\s*수\s*있(?:어|어요|나요|니)?"
	r"|(?:이\s*)?서비스(?:는|의)?\s*(?:무슨\s*|어떤\s*)?기능(?:이|은)?(?:\s*(?:있어|있어요|있나요|뭐야|뭐예요|알려\s*줘|알려\s*주세요))?"
)
# ④ 일상 잡담: 날씨, 배고프다, 심심해, 잘 지내?
_SMALLTALK_WORDS = (
	r"(?:오늘\s*)?날씨(?:가|는)?(?:\s*(?:어때|어때요|좋다|좋네|좋네요|좋아요))?"
	r"|배고프다|배고파(?:요)?|심심해(?:요)?|심심하다"
	r"|잘\s*지내(?:요|니|셨어요|세요)?"
)
_CHAT_WORDS = "|".join([_GREETING_WORDS, _REACTION_WORDS, _BOT_WORDS, _SMALLTALK_WORDS])
GREETING_RE = re.compile(
	rf"^\s*(?:{_CHAT_WORDS})(?:{_SEP}*(?:{_CHAT_WORDS}))*{_SEP}*$",
	re.IGNORECASE,
)

# 정규식·키워드로 정하지 못한 질문을 LLM이 분류할 때 쓰는 지시문 (RouteDecision.route의 description과 함께 전달됨)
ROUTE_SYSTEM_PROMPT = (
	"너는 경제 분석 보고서 질의응답 서비스의 질문 분류기다. "
	"사용자의 말이 보고서 내용을 찾아 답해야 하는 질문이면 'rewrite', "
	"인사·감사·잡담처럼 보고서 검색이 필요 없으면 'chat'을 고른다."
)


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
	"""validate 노드 다음 갈 곳을 고른다 (명세서 순서대로 확인).

	1) state['error']가 있으면(validate 노드에서 InvalidInputError) 'error' → error_reply 노드
	2) 질문 전체가 인사·감사·잡담 표현이면(GREETING_RE) 'chat' → chat 노드 (3단계 extract_keywords 전에 갈라짐)
	3) extract_keywords(질문) 결과가 있으면 'rewrite' → 검색 흐름
	4) 그래도 애매하면(키워드가 하나도 없음. 예: 'ㅇㅇ', '...') get_chat_model(temperature=0).with_structured_output(RouteDecision)으로 분류

	라우팅 함수는 state를 바꾸지 않는다 (반환값으로 갈 노드만 고른다).
	extract_keywords·get_chat_model은 함수 안에서 import한다: 두 모듈은 import할 때 설정(.env)·DB·Chroma 모듈을
	함께 불러오므로, 그래프 파일을 import만 해도 그것들이 필요해지는 것을 막는다.
	"""
	if state.get("error"):
		return "error"

	question = state.get("question") or ""
	# 인사·감사·잡담은 여기서 끝난다 (extract_keywords·LLM을 부르지 않음)
	if GREETING_RE.match(question):
		return "chat"

	from hri.retriever.search import extract_keywords

	if extract_keywords(question):
		return "rewrite"

	from hri.llm.llm_client import get_chat_model

	classifier = get_chat_model(temperature=0).with_structured_output(RouteDecision)
	decision = classifier.invoke([
		{"role": "system", "content": ROUTE_SYSTEM_PROMPT},
		{"role": "user", "content": question},
	])
	return decision.route


def route_after_grade(state: QAState) -> Literal["generate", "no_answer"]:
	"""grade 다음 갈 곳: has_context(state['docs'])가 True면 'generate', 아니면 'no_answer'.

	has_context()는 검색 결과 청크가 하나라도 있는지만 보는 함수다 (LLM 호출 없음, 장유빈 rag_prompt).
	QAState에 grade 결과를 적는 키가 없으므로 분기 함수가 has_context()를 직접 부른다.
	"""
	if has_context(state.get("docs") or []):
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
