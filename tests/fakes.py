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


# ─────────────────────────────────────────────────────────────
# 업로드 그래프 저장(persist) 테스트용 가짜 DB·벡터DB (WBS 3.8.3)
# ─────────────────────────────────────────────────────────────

class FakeConnection:
	"""get_connection()이 돌려주는 pymysql 연결 흉내. commit·rollback·close 호출을 events에 기록한다.

	with 문으로 쓰면 블록이 끝날 때 close()가 불린다 (진짜 pymysql 연결과 같음).
	"""

	def __init__(self, events: list):
		self.events = events

	def commit(self):
		self.events.append("commit")

	def rollback(self):
		self.events.append("rollback")

	def close(self):
		self.events.append("close")

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		self.close()
		return False


class FakeIngestStore:
	"""persist 노드가 부르는 DB·벡터DB 함수의 가짜. 호출 순서를 events에, 인자를 calls에 기록한다.

	- fail_at: 이 이름의 단계에서 RuntimeError를 낸다 (rollback 확인용).
	  'insert_report' · 'insert_sections' · 'insert_tables' · 'insert_chunks' · 'add_chunks' · 'commit' · 'delete_report_vectors'
	- report_id: insert_report가 돌려줄 번호
	"""

	def __init__(self, report_id: int = 7, fail_at: str | None = None):
		self.report_id = report_id
		self.fail_at = fail_at
		self.events: list = []
		self.calls: dict = {}
		self.connections: list = []

	def _step(self, name: str, *args):
		self.events.append(name)
		self.calls[name] = args
		if self.fail_at == name:
			raise RuntimeError(f"{name} 실패")

	def get_connection(self):
		self.events.append("get_connection")
		conn = FakeConnection(self.events)
		if self.fail_at == "commit":
			def failing_commit():
				self.events.append("commit")
				raise RuntimeError("commit 실패")
			conn.commit = failing_commit
		self.connections.append(conn)
		return conn

	def insert_report(self, conn, report):
		self._step("insert_report", conn, report)
		return self.report_id

	def insert_sections(self, conn, report_id, sections):
		self._step("insert_sections", conn, report_id, sections)
		return len(sections)

	def insert_tables(self, conn, report_id, tables):
		self._step("insert_tables", conn, report_id, tables)
		return len(tables)

	def insert_chunks(self, conn, report_id, chunks):
		self._step("insert_chunks", conn, report_id, chunks)
		return len(chunks)

	def add_chunks(self, chunks):
		self._step("add_chunks", chunks)
		return len(chunks)

	def delete_report_vectors(self, report_id):
		self._step("delete_report_vectors", report_id)


def install_ingest_store(monkeypatch, store: FakeIngestStore, chunk_size: int = 500, chunk_overlap: int = 50) -> FakeIngestStore:
	"""split·persist 노드가 부르는 진짜 모듈의 함수를 가짜로 바꿔 끼운다 (DB·Chroma·.env 없이 실행).

	- hri.config.settings.load_settings : CHUNK_SIZE·CHUNK_OVERLAP만 쓰는 가짜 Settings
	- hri.dao.db.get_connection · hri.dao.report_dao.insert_* · hri.vector_store.chroma_store.add_chunks·delete_report_vectors
	"""
	import hri.config.settings as settings_module
	import hri.dao.db as db
	import hri.dao.report_dao as report_dao
	import hri.vector_store.chroma_store as chroma_store
	from hri.domain.schemas import Settings

	settings = Settings(mysql_host="localhost", mysql_user="test", mysql_password="test", mysql_database="test",
		chunk_size=chunk_size, chunk_overlap=chunk_overlap)
	monkeypatch.setattr(settings_module, "load_settings", lambda: settings)
	monkeypatch.setattr(db, "get_connection", store.get_connection)
	for name in ("insert_report", "insert_sections", "insert_tables", "insert_chunks"):
		monkeypatch.setattr(report_dao, name, getattr(store, name), raising=False)
	for name in ("add_chunks", "delete_report_vectors"):
		monkeypatch.setattr(chroma_store, name, getattr(store, name))
	return store
