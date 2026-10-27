"""Tool Calling 흐름 · build_agent_graph, agent_node (엄정현)

[뼈대 단계 · 3.8.8] 노드 연결만 명세대로 해 두고, 노드는 아무 값도 바꾸지 않는 가짜({} 반환)다.
agent_node와 tools(ToolNode(TOOLS)) 노드는 3.8.7에서 채운다.

흐름 (LangGraph 워크플로우 명세서 build_agent_graph 행)
	START → agent → tools_condition
		├─ 마지막 AIMessage에 tool_calls가 있으면 'tools' → tools → agent (반복)
		└─ 없으면 END
run_agent_with_tools()가 recursion_limit=GRAPH_RECURSION_LIMIT로 실행해 무한 반복을 막는다.
compile은 registry.get_agent_graph()가 한 번만 한다.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import tools_condition

from hri.domain.schemas import AgentState


def _skeleton_node(state: AgentState) -> dict:
	"""뼈대용 가짜 노드: state를 바꾸지 않는다.

	tools 자리에 임시로 쓴다. 3.8.7에서 ToolNode(TOOLS)로 바꾼다
	(TOOLS는 hri.router.tool_router, 김희진 담당. 아직 정의되지 않음).
	"""
	return {}


def agent_node(state: AgentState) -> dict:
	"""[뼈대] 3.8.7에서 구현: system 메시지 + state['messages']로
	get_chat_model(temperature=0).bind_tools(TOOLS).invoke() → {'messages': [AIMessage]}."""
	return {}


def build_agent_graph() -> StateGraph:
	"""에이전트 그래프를 노드·엣지까지 연결해 돌려준다 (compile 전 StateGraph)."""
	graph = StateGraph(AgentState)

	graph.add_node("agent", agent_node)
	graph.add_node("tools", _skeleton_node)

	graph.add_edge(START, "agent")
	# tools_condition: 마지막 메시지에 tool_calls가 있으면 'tools', 없으면 END('__end__')
	graph.add_conditional_edges("agent", tools_condition, ["tools", END])
	graph.add_edge("tools", "agent")
	return graph
