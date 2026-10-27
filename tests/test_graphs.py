"""그래프 분기·통합 테스트 · test_*_graph (엄정현)

[뼈대 단계 · 3.8.8] 4개 그래프가 명세대로 연결되어 compile되는지, registry가 한 번만 만드는지 확인한다.
노드는 아직 가짜({} 반환)라서 입력으로 넣은 값(error·docs·sections 등)으로 분기만 확인한다 (네트워크·DB·LLM 없이 실행).
FakeToolChatModel을 쓰는 노드 동작 테스트와 ingest 통합 테스트는 3.8.9에서 이 파일에 추가한다.

실행: poetry run python -m pytest tests/test_graphs.py -v
"""

import subprocess
import sys

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

from hri.graph import registry
from hri.graph.checkpointer import get_checkpointer
from hri.graph.visualize import draw_graphs

GETTERS = [registry.get_ingest_graph, registry.get_qa_graph, registry.get_summary_graph, registry.get_agent_graph]


# 테스트마다 그래프·체크포인터를 새로 만들게 캐시를 비운다 (앞 테스트의 대화 기록이 남지 않게)
@pytest.fixture(autouse=True)
def clear_graph_cache():
	for getter in GETTERS:
		getter.cache_clear()
	get_checkpointer.cache_clear()
	yield
	for getter in GETTERS:
		getter.cache_clear()
	get_checkpointer.cache_clear()


# 그래프를 실행하며 실행된 노드 이름을 순서대로 모은다 (stream_mode='updates': 노드가 끝날 때마다 {노드: 바뀐 값})
def run_nodes(graph, inputs, config=None):
	nodes = []
	for update in graph.stream(inputs, config=config, stream_mode="updates"):
		nodes.extend(update.keys())
	return nodes


# 그래프 구조에서 (출발 노드, 도착 노드) 쌍을 모은다
def edges_of(graph):
	return {(e.source, e.target) for e in graph.get_graph().edges}


def nodes_of(graph):
	return set(graph.get_graph().nodes) - {"__start__", "__end__"}


# ─────────────────────────────────────────────────────────────
# 1. registry: 지연 싱글턴
# ─────────────────────────────────────────────────────────────

# [확인 1] registry를 import해도 그래프 파일은 아직 import되지 않아야 한다 (build import는 함수 안 → 순환 import 방지)
def test_registry_import_does_not_import_graph_modules():
	code = (
		"import sys, hri.graph.registry; "
		"mods = ['hri.graph.ingest_graph', 'hri.graph.qa_graph', 'hri.graph.summary_graph', 'hri.graph.agent_graph']; "
		"print([m for m in mods if m in sys.modules])"
	)
	out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
	assert out.stdout.strip() == "[]"


# [확인 2] get_*_graph()는 compile된 그래프를 돌려주고, 두 번 불러도 같은 객체여야 한다 (lru_cache)
@pytest.mark.parametrize("getter", GETTERS)
def test_get_graph_returns_same_compiled_graph(getter):
	first = getter()
	assert isinstance(first, CompiledStateGraph)
	assert getter() is first


# [확인 3] cache_clear() 뒤에는 새로 만들어야 한다 (테스트에서 가짜 모델로 바꿀 때 사용)
@pytest.mark.parametrize("getter", GETTERS)
def test_cache_clear_rebuilds_graph(getter):
	first = getter()
	getter.cache_clear()
	assert getter() is not first


# [확인 4] 체크포인터는 qa 그래프에만 붙고, get_checkpointer()의 하나뿐인 객체여야 한다
def test_only_qa_graph_has_checkpointer():
	assert registry.get_qa_graph().checkpointer is get_checkpointer()
	assert get_checkpointer() is get_checkpointer()
	for getter in (registry.get_ingest_graph, registry.get_summary_graph, registry.get_agent_graph):
		assert getter().checkpointer is None


# ─────────────────────────────────────────────────────────────
# 2. 노드·엣지가 명세서(LangGraph 워크플로우 명세서 build_*_graph 행)와 같은지
# ─────────────────────────────────────────────────────────────

# [확인 5] 그래프별 노드 이름
@pytest.mark.parametrize(
	("getter", "names"),
	[
		(registry.get_ingest_graph, {
			"validate", "load_text", "extract_tables", "extract_charts", "process_charts",
			"split", "summarize_tables", "persist",
		}),
		(registry.get_qa_graph, {
			"validate", "chat", "error_reply", "rewrite", "retrieve", "grade",
			"no_answer", "generate", "sources", "suggest", "save_log",
		}),
		(registry.get_summary_graph, {"load_cache", "load_sections", "summarize_section", "three_lines", "save"}),
		(registry.get_agent_graph, {"agent", "tools"}),
	],
)
def test_graph_nodes_match_spec(getter, names):
	assert nodes_of(getter()) == names


# [확인 6] 업로드 그래프: 검증 → 추출 3개 병렬 → 차트는 process_charts → 세 갈래가 split으로 모임 → 저장
def test_ingest_edges():
	edges = edges_of(registry.get_ingest_graph())
	assert {
		("__start__", "validate"),
		("validate", "load_text"), ("validate", "extract_tables"), ("validate", "extract_charts"), ("validate", "__end__"),
		("extract_charts", "process_charts"),
		("load_text", "split"), ("extract_tables", "split"), ("process_charts", "split"),
		("split", "summarize_tables"), ("summarize_tables", "persist"), ("persist", "__end__"),
	} == edges


# [확인 7] 질의응답 그래프: 분류 3갈래 → 근거 분기 → [sources ∥ suggest] → save_log
def test_qa_edges():
	edges = edges_of(registry.get_qa_graph())
	assert {
		("__start__", "validate"),
		("validate", "chat"), ("validate", "rewrite"), ("validate", "error_reply"),
		("rewrite", "retrieve"), ("retrieve", "grade"),
		("grade", "generate"), ("grade", "no_answer"),
		("generate", "sources"), ("generate", "suggest"),
		("sources", "save_log"), ("suggest", "save_log"),
		("chat", "save_log"), ("no_answer", "save_log"), ("error_reply", "save_log"),
		("save_log", "__end__"),
	} == edges


# [확인 8] 요약 그래프: 캐시 → 섹션 → 섹션별 요약 → 3줄 → 저장
def test_summary_edges():
	edges = edges_of(registry.get_summary_graph())
	assert {
		("__start__", "load_cache"),
		("load_cache", "load_sections"), ("load_cache", "__end__"),
		("load_sections", "summarize_section"), ("load_sections", "__end__"),
		("summarize_section", "three_lines"), ("three_lines", "save"), ("save", "__end__"),
	} == edges


# [확인 9] 에이전트 그래프: agent ↔ tools 반복, 도구 호출이 없으면 끝
def test_agent_edges():
	edges = edges_of(registry.get_agent_graph())
	assert {("__start__", "agent"), ("agent", "tools"), ("agent", "__end__"), ("tools", "agent")} == edges


# ─────────────────────────────────────────────────────────────
# 3. 가짜 노드로 실제 실행해 분기 확인
# ─────────────────────────────────────────────────────────────

# [확인 10] 업로드 정상: 8개 노드가 모두 실행되고, split은 세 갈래가 끝난 뒤 한 번만 실행
def test_ingest_runs_all_nodes():
	nodes = run_nodes(registry.get_ingest_graph(), {"file_path": "data/raw/sample.pdf", "user_id": "tester"})
	assert nodes[0] == "validate"
	assert set(nodes[1:4]) == {"load_text", "extract_tables", "extract_charts"}
	assert nodes[4:] == ["process_charts", "split", "summarize_tables", "persist"]


# [확인 11] 업로드 검증 실패: state['error']가 있으면 validate 다음 바로 끝
def test_ingest_stops_when_validate_fails():
	nodes = run_nodes(registry.get_ingest_graph(), {"file_path": "a.txt", "user_id": "tester", "error": "PDF 파일만 업로드할 수 있습니다"})
	assert nodes == ["validate"]


# [확인 12] 질의응답 3갈래 + 근거 분기가 save_log로 끝나야 한다
@pytest.mark.parametrize(
	("inputs", "expected"),
	[
		({"question": "금리 전망은?", "docs": ["근거 청크"]},
		 ["validate", "rewrite", "retrieve", "grade", "generate", {"sources", "suggest"}, "save_log"]),
		({"question": "금리 전망은?", "docs": []},
		 ["validate", "rewrite", "retrieve", "grade", "no_answer", "save_log"]),
		({"question": "", "error": "질문을 입력해 주세요"},
		 ["validate", "error_reply", "save_log"]),
	],
	ids=["근거_있음", "근거_없음", "입력_오류"],
)
def test_qa_routes(inputs, expected):
	config = {"configurable": {"thread_id": "test-session"}}
	nodes = run_nodes(registry.get_qa_graph(), inputs, config)
	# {"sources", "suggest"}처럼 집합으로 적은 칸은 같은 단계에서 병렬 실행되어 순서가 정해지지 않은 노드들
	flat = []
	for step in expected:
		if isinstance(step, set):
			assert set(nodes[len(flat):len(flat) + len(step)]) == step
			flat.extend(nodes[len(flat):len(flat) + len(step)])
		else:
			flat.append(step)
	assert nodes == flat


# [확인 13] 질의응답 그래프는 thread_id가 없으면 실행되지 않아야 한다 (체크포인터가 붙어 있음)
def test_qa_requires_thread_id():
	with pytest.raises(ValueError):
		registry.get_qa_graph().invoke({"question": "q"})


# [확인 14] 요약: 섹션 수만큼 summarize_section이 실행되고 그 뒤 three_lines·save
def test_summary_fans_out_per_section():
	nodes = run_nodes(registry.get_summary_graph(), {"report_id": 1, "sections": ["서론", "본론", "결론"]})
	assert nodes == ["load_cache", "load_sections", "summarize_section", "summarize_section", "summarize_section", "three_lines", "save"]


# [확인 15] 요약: state['error'](섹션 0개)면 load_sections 다음 바로 끝
def test_summary_stops_on_error():
	nodes = run_nodes(registry.get_summary_graph(), {"report_id": 1, "sections": [], "error": "요약할 섹션이 없습니다"})
	assert nodes == ["load_cache", "load_sections"]


# [확인 16] 에이전트: 마지막 메시지에 도구 호출이 없으면 agent 한 번으로 끝
def test_agent_ends_without_tool_calls():
	nodes = run_nodes(registry.get_agent_graph(), {"messages": [HumanMessage("요약해줘")], "report_ids": [1]})
	assert nodes == ["agent"]


# [확인 17] 에이전트: 도구 호출이 있으면 tools ↔ agent를 반복하고, recursion_limit을 넘으면 GraphRecursionError
#           (가짜 agent 노드는 메시지를 바꾸지 않아 도구 호출이 계속 남으므로 끝나지 않는다 → 한도에서 멈추는지 확인)
def test_agent_loops_until_recursion_limit():
	call = AIMessage(content="", tool_calls=[{"name": "summarize_reports", "args": {}, "id": "call_1"}])
	with pytest.raises(GraphRecursionError):
		registry.get_agent_graph().invoke(
			{"messages": [HumanMessage("요약해줘"), call], "report_ids": [1]},
			config={"recursion_limit": 8},
		)


# ─────────────────────────────────────────────────────────────
# 4. 구조도 문서화
# ─────────────────────────────────────────────────────────────

# [확인 18] draw_graphs()는 4개 그래프를 <out_dir>/<이름>.md에 Mermaid로 저장하고 경로를 돌려준다
def test_draw_graphs_writes_mermaid(tmp_path):
	paths = draw_graphs(out_dir=str(tmp_path))
	assert [p.replace("\\", "/").rsplit("/", 1)[-1] for p in paths] == ["ingest.md", "qa.md", "summary.md", "agent.md"]
	for path in paths:
		text = open(path, encoding="utf-8").read()
		assert "```mermaid" in text and "graph TD" in text
	assert "process_charts" in open(paths[0], encoding="utf-8").read()
