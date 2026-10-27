"""테스트용 가짜 모델 · FakeToolChatModel: bind_tools·with_structured_output 구현 (엄정현)

langchain의 GenericFakeChatModel은 bind_tools를 구현하지 않고, with_structured_output도 bind_tools를 쓰므로
도구를 붙이는 그래프(agent_graph)·구조화 출력을 쓰는 함수(route_question 등)를 테스트할 수 없다.
FakeToolChatModel은 미리 넣어 둔 응답을 차례로 돌려주고, 받은 메시지·붙인 도구·요청한 양식을 기록한다 (네트워크·API 키 없이 실행).

사용
	fake = FakeToolChatModel(responses=[AIMessage(content="", tool_calls=[...]), AIMessage(content="완료")])
	get_chat_model을 lambda **kw: fake 로 바꿔 끼운 뒤 그래프를 실행한다.
"""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field


class FakeToolChatModel(BaseChatModel):
	"""미리 넣은 응답(AIMessage 또는 Pydantic 객체)을 순서대로 돌려주는 가짜 채팅 모델.

	- invoke()      : responses에서 AIMessage를 하나 꺼내 돌려준다 (tool_calls가 있으면 도구 호출 응답)
	- bind_tools()  : 붙인 도구를 bound_tools에 기록하고 자기 자신을 돌려준다
	- with_structured_output(schema): responses에서 Pydantic 객체를 하나 꺼내 돌려주는 Runnable을 돌려준다
	- calls         : 모델이 받은 메시지 목록을 호출마다 기록한다
	응답이 떨어지면 AssertionError로 알려 준다 (예상보다 LLM을 더 부른 것).
	"""

	responses: list[Any] = Field(default_factory=list)
	calls: list[list[BaseMessage]] = Field(default_factory=list)
	bound_tools: list[Any] = Field(default_factory=list)
	structured_schemas: list[Any] = Field(default_factory=list)

	@property
	def _llm_type(self) -> str:
		return "fake-tool-chat"

	def _next(self) -> Any:
		assert self.responses, "FakeToolChatModel: 미리 넣은 응답을 다 썼습니다 (예상보다 LLM을 더 불렀습니다)"
		return self.responses.pop(0)

	def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
		self.calls.append(list(messages))
		response = self._next()
		assert isinstance(response, AIMessage), f"invoke 차례인데 AIMessage가 아닌 {type(response).__name__}가 들어 있습니다"
		# 같은 객체를 다시 쓰면 add_messages가 같은 id로 보고 덮어쓰므로 복사해서 돌려준다
		return ChatResult(generations=[ChatGeneration(message=response.model_copy())])

	def bind_tools(self, tools: list[Any], **kwargs: Any) -> "FakeToolChatModel":
		self.bound_tools = list(tools)
		return self

	def with_structured_output(self, schema: Any, **kwargs: Any) -> RunnableLambda:
		self.structured_schemas.append(schema)

		def _respond(messages: Any) -> Any:
			self.calls.append(list(messages) if isinstance(messages, list) else [messages])
			response = self._next()
			assert isinstance(response, schema), f"{schema.__name__} 차례인데 {type(response).__name__}가 들어 있습니다"
			return response

		return RunnableLambda(_respond)
