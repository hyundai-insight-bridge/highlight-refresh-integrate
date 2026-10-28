"""업로드 분할·요약·저장 노드 테스트 · split_node, summarize_tables_node, persist_node (엄정현, WBS 3.8.3)

네트워크·DB·Chroma·LLM·.env 없이 실행한다.
- split_sections·split_text(김희진 text_splitter)는 진짜 함수를 쓴다
- 설정(CHUNK_SIZE·CHUNK_OVERLAP)·DB·Chroma는 tests/fakes.py의 FakeIngestStore로 바꿔 끼운다
- summarize_tables(엄정현 table_loader, 아직 미구현)는 가짜로 바꿔 끼운다

실행: poetry run python -m pytest tests/test_ingest_nodes.py -v
"""

from datetime import date

import pytest

import hri.loader.table_loader as table_loader
from hri.domain.schemas import Chunk, Page, Report, Section, Table
from hri.graph.ingest_graph import (
	NO_SECTION_WARNING,
	PENDING_TABLE_TEXT,
	persist_node,
	split_node,
	summarize_tables_node,
)
from tests.fakes import FakeIngestStore, install_ingest_store


# 목차 제목 3개(1·2·3)가 있는 5쪽짜리 본문. 섹션: 1쪽(1. 개요) · 2~3쪽(2. 경기 동향) · 5쪽(3. 전망)
PAGES = [
	Page(page=1, text="1. 개요\n올해 경제는 완만하게 회복하였다."),
	Page(page=2, text="2. 경기 동향\n소비가 늘어나고 있다.\n수출도 증가하였다."),
	Page(page=3, text="투자는 아직 부진하다."),
	Page(page=5, text="3. 전망\n내년 성장률은 2%대로 예상된다."),
]


def make_table(page, source_type="table", caption="< 주요 지표 >"):
	return Table(page=page, caption=caption, markdown="| 지표 | 값 |\n|---|---|\n| 성장률 | 2.0 |", source_type=source_type)


# ─────────────────────────────────────────────────────────────
# 1. split_node
# ─────────────────────────────────────────────────────────────

# [확인 1] 섹션 3개, 섹션별 텍스트 청크, 표·차트 청크(쪽이 속한 섹션 번호·doc_id·임시 글), chunk_no는 0부터 차례로
def test_split_node_sections_and_chunks(monkeypatch):
	install_ingest_store(monkeypatch, FakeIngestStore())
	table, chart = make_table(page=3), make_table(page=5, source_type="chart", caption="[그림 1]")

	result = split_node({"pages": PAGES, "tables": [table, chart]})

	assert [(s.section_no, s.title, s.start_page, s.end_page) for s in result["sections"]] == [
		(0, "1. 개요", 1, 1), (1, "2. 경기 동향", 2, 3), (2, "3. 전망", 5, 5),
	]
	chunks = result["chunks"]
	assert [c.chunk_no for c in chunks] == list(range(len(chunks)))
	text_chunks = [c for c in chunks if c.chunk_type == "text"]
	assert [c.section_no for c in text_chunks] == [0, 1, 2]
	assert all(c.doc_id is None and c.report_id is None for c in text_chunks)
	assert [(c.chunk_type, c.section_no, c.page, c.doc_id, c.text) for c in chunks[-2:]] == [
		("table", 1, 3, table.doc_id, PENDING_TABLE_TEXT),
		("chart", 2, 5, chart.doc_id, PENDING_TABLE_TEXT),
	]
	assert "warnings" not in result


# [확인 2] CHUNK_SIZE·CHUNK_OVERLAP 설정값으로 텍스트를 자른다 (chunk_size를 작게 하면 청크가 늘어남)
def test_split_node_uses_chunk_settings(monkeypatch):
	install_ingest_store(monkeypatch, FakeIngestStore(), chunk_size=20, chunk_overlap=5)
	result = split_node({"pages": PAGES, "tables": []})
	assert len(result["chunks"]) > 3
	assert all(len(c.text) <= 20 for c in result["chunks"])


# [확인 3] 섹션 범위 밖 쪽(4쪽)의 표는 그 앞에서 시작한 마지막 섹션에 붙는다
def test_split_node_table_outside_sections(monkeypatch):
	install_ingest_store(monkeypatch, FakeIngestStore())
	result = split_node({"pages": PAGES, "tables": [make_table(page=4)]})
	assert result["chunks"][-1].section_no == 1


# [확인 4] 섹션이 하나도 없으면(예: 모두 스캔본) 표·차트 청크를 만들지 않고 경고를 남긴다
def test_split_node_without_sections(monkeypatch):
	install_ingest_store(monkeypatch, FakeIngestStore())
	result = split_node({"pages": [Page(page=1, text="", is_scanned=True)], "tables": [make_table(page=1)]})
	assert result["sections"] == [] and result["chunks"] == []
	assert result["warnings"] == [NO_SECTION_WARNING]


# ─────────────────────────────────────────────────────────────
# 2. summarize_tables_node
# ─────────────────────────────────────────────────────────────

# [확인 5] 표·차트 청크의 글을 '캡션\n요약'으로 바꾸고, 반환 키는 summarized_tables·chunks ('tables'로 돌려주지 않음)
def test_summarize_tables_node(monkeypatch):
	install_ingest_store(monkeypatch, FakeIngestStore())
	table, chart = make_table(page=3), make_table(page=5, source_type="chart", caption=None)
	state = split_node({"pages": PAGES, "tables": [table, chart]})
	state["tables"] = [table, chart]

	def fake_summarize(tables):
		return [t.model_copy(update={"summary": f"{t.page}쪽 요약"}) for t in tables]

	monkeypatch.setattr(table_loader, "summarize_tables", fake_summarize, raising=False)
	result = summarize_tables_node(state)

	assert set(result) == {"summarized_tables", "chunks"}
	assert [t.summary for t in result["summarized_tables"]] == ["3쪽 요약", "5쪽 요약"]
	by_type = {c.chunk_type: c.text for c in result["chunks"] if c.chunk_type != "text"}
	assert by_type == {"table": "< 주요 지표 >\n3쪽 요약", "chart": "5쪽 요약"}
	texts_before = [c.text for c in state["chunks"] if c.chunk_type == "text"]
	assert [c.text for c in result["chunks"] if c.chunk_type == "text"] == texts_before


# [확인 6] 표·차트가 0개면 summarize_tables(LLM)를 부르지 않고 그대로 통과한다
def test_summarize_tables_node_without_tables(monkeypatch):
	def must_not_call(tables):
		raise AssertionError("표가 없는데 summarize_tables를 불렀습니다")

	monkeypatch.setattr(table_loader, "summarize_tables", must_not_call, raising=False)
	assert summarize_tables_node({"tables": [], "chunks": []}) == {"summarized_tables": []}


# ─────────────────────────────────────────────────────────────
# 3. persist_node
# ─────────────────────────────────────────────────────────────

def persist_state():
	sections = [Section(section_no=0, title="1. 개요", start_page=1, end_page=2, text="1. 개요\n본문")]
	table = make_table(page=2).model_copy(update={"summary": "요약"})
	chunks = [
		Chunk(chunk_no=0, section_no=0, page=1, chunk_type="text", text="본문"),
		Chunk(chunk_no=1, section_no=0, page=2, chunk_type="table", text="< 주요 지표 >\n요약", doc_id=table.doc_id),
	]
	return {
		"file_path": "data/raw/report.pdf", "user_id": "tester",
		"meta": {"title": "2026년 경제전망", "publisher": "현대경제연구원", "published_date": date(2026, 7, 31)},
		"pages": [Page(page=3, text="..."), Page(page=12, text="...")],
		"sections": sections, "summarized_tables": [table], "chunks": chunks,
	}


# [확인 7] 정상 저장: 한 연결로 insert_report → insert_sections → insert_tables → insert_chunks → add_chunks → commit → close
def test_persist_node_success(monkeypatch):
	store = install_ingest_store(monkeypatch, FakeIngestStore(report_id=7))
	state = persist_state()

	result = persist_node(state)

	assert store.events == ["get_connection", "insert_report", "insert_sections", "insert_tables", "insert_chunks", "add_chunks", "commit", "close"]
	conn = store.connections[0]
	assert all(store.calls[name][0] is conn for name in ("insert_report", "insert_sections", "insert_tables", "insert_chunks"))
	report = store.calls["insert_report"][1]
	assert isinstance(report, Report)
	assert (report.title, report.publisher, report.published_date, report.page_count, report.file_path, report.uploaded_by) == (
		"2026년 경제전망", "현대경제연구원", date(2026, 7, 31), 12, "data/raw/report.pdf", "tester")
	assert store.calls["insert_tables"][2] == state["summarized_tables"]
	assert [c.report_id for c in store.calls["add_chunks"][0]] == [7, 7]                # Chroma에는 report_id를 채운 청크
	assert result == {"report_id": 7, "counts": {"text": 1, "table": 1, "chart": 0}}


# [확인 8] 중간 실패(rollback): 어느 단계에서 실패해도 rollback → delete_report_vectors(report_id) → 원래 예외를 다시 던진다
#          commit은 실패한 경우가 아니면 부르지 않는다
@pytest.mark.parametrize("fail_at", ["insert_sections", "insert_tables", "insert_chunks", "add_chunks", "commit"])
def test_persist_node_rollback(monkeypatch, fail_at):
	store = install_ingest_store(monkeypatch, FakeIngestStore(report_id=7, fail_at=fail_at))

	with pytest.raises(RuntimeError, match=f"{fail_at} 실패"):
		persist_node(persist_state())

	assert store.events[-3:] == ["rollback", "delete_report_vectors", "close"]
	assert store.calls["delete_report_vectors"] == (7,)
	if fail_at != "commit":
		assert "commit" not in store.events


# [확인 9] insert_report에서 실패하면 report_id가 없으므로 rollback만 하고 벡터 정리는 하지 않는다
def test_persist_node_rollback_before_report_id(monkeypatch):
	store = install_ingest_store(monkeypatch, FakeIngestStore(fail_at="insert_report"))
	with pytest.raises(RuntimeError, match="insert_report 실패"):
		persist_node(persist_state())
	assert store.events == ["get_connection", "insert_report", "rollback", "close"]


# [확인 10] 벡터 정리(delete_report_vectors)까지 실패해도 원래 오류를 그대로 던지고, 정리 실패는 로그로 남긴다
def test_persist_node_cleanup_failure_keeps_original_error(monkeypatch, caplog):
	store = FakeIngestStore(report_id=7, fail_at="add_chunks")
	install_ingest_store(monkeypatch, store)

	def failing_delete(report_id):
		store.events.append("delete_report_vectors")
		raise ConnectionError("Chroma 연결 끊김")

	import hri.vector_store.chroma_store as chroma_store
	monkeypatch.setattr(chroma_store, "delete_report_vectors", failing_delete)

	with pytest.raises(RuntimeError, match="add_chunks 실패"):
		persist_node(persist_state())
	assert "보고서 7 벡터 정리 실패" in caplog.text
