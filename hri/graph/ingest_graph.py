"""보고서 업로드 흐름 · build_ingest_graph, validate_node, route_after_validate, load_text_node, extract_tables_node, process_charts_node, split_node, summarize_tables_node, persist_node (엄정현)

[3.8.1] 그래프 구성(build_ingest_graph)·검증 노드(validate_node)·검증 분기(route_after_validate)를 명세대로 채웠다.
[3.8.3] 분할(split_node)·표 요약(summarize_tables_node)·저장(persist_node) 노드를 명세대로 채웠다.
	- split: 본문을 섹션(부모)과 검색용 청크(자식)로 나누고, 표·차트도 청크로 만든다
	- summarize_tables: 표·차트마다 1~2문장 요약을 만들어 표·차트 청크의 검색용 글(캡션+요약)로 넣는다
	- persist: DB(MySQL)와 벡터DB(Chroma)에 한 번에 저장한다. 중간에 실패하면 모두 되돌린다(rollback)
추출 노드(load_text·extract_tables·extract_charts·process_charts)는 아직 가짜({} 반환)다. 3.8.2에서 채운다.

흐름 (LangGraph 워크플로우 명세서 build_ingest_graph 행)
	START → validate → route_after_validate
		├─ 실패(state['error']) → END
		└─ 통과 → [load_text ∥ extract_tables ∥ extract_charts] (같은 단계에서 병렬 실행)
	extract_charts → process_charts
	[load_text, extract_tables, process_charts] 세 갈래가 모두 끝나면 → split → summarize_tables → persist → END
compile은 registry.get_ingest_graph()가 한 번만 한다.
"""

import logging
from collections import Counter

from langgraph.graph import END, START, StateGraph

from hri.domain.schemas import Chunk, IngestState, Report, Section, Table

logger = logging.getLogger(__name__)

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


# ── 명세서에 정해지지 않은 값 (정해지면 아래 값만 바꾼다) ─────────────────────────────
# TODO(확인 필요): split 단계에서 표·차트 청크에 잠깐 넣어 두는 글.
#   명세서는 '표·차트 청크의 text는 summarize_tables에서 채움'인데, Chunk.text는 빈 글을 받지 않는다(min_length=1).
#   그래서 summarize_tables 노드가 '캡션+요약'으로 바꾸기 전까지 이 글을 넣어 둔다 (DB·벡터DB에는 저장되지 않음).
PENDING_TABLE_TEXT = "(요약 전)"

# TODO(확인 필요): 섹션을 하나도 찾지 못했을 때(예: 모든 쪽이 스캔본) 남기는 경고.
#   표·차트 청크는 섹션 번호(sections FK)가 있어야 저장할 수 있으므로 이 경우 표·차트 청크를 만들지 않는다.
NO_SECTION_WARNING = "본문 섹션을 찾지 못해 표·차트를 검색 청크로 만들지 않았습니다"


def _section_no_for_page(sections: list[Section], page: int) -> int:
	"""표·차트가 있는 쪽(page)이 속한 섹션 번호를 찾는다 (명세서: 'page가 속한 섹션의 section_no').

	- start_page ≤ page ≤ end_page인 섹션을 찾는다.
	- TODO(확인 필요): 어느 섹션 범위에도 없는 쪽이면(섹션 사이의 빈 쪽 등) 그 쪽보다 앞에서 시작한 마지막 섹션,
	  그것도 없으면 첫 섹션으로 붙인다. 명세서에는 범위 밖일 때의 규칙이 없다.
	"""
	for section in sections:
		if section.start_page <= page <= section.end_page:
			return section.section_no
	before = [s for s in sections if s.start_page <= page]
	return (before[-1] if before else sections[0]).section_no


def split_node(state: IngestState) -> dict:
	"""[분할 노드] 정제한 쪽(pages)을 섹션과 검색용 청크로 나눈다. {'sections', 'chunks'}를 돌려준다.

	순서 (명세서 split_node 행)
	1. split_sections(pages)  : 목차 제목(Ⅰ./1./가.)을 기준으로 섹션(부모, 답변 근거 원문)을 나눈다 (김희진 text_splitter)
	2. 섹션마다 split_text(섹션 글, CHUNK_SIZE, CHUNK_OVERLAP) : 검색용 텍스트 청크(자식)로 자른다
	   - CHUNK_SIZE·CHUNK_OVERLAP은 .env 설정값(Settings.chunk_size·chunk_overlap, 기본 500·50)
	   - TODO(확인 필요): 텍스트 청크의 page(출처 쪽)는 섹션 시작 쪽으로 넣는다. 청크마다 정확한 쪽을 찾는 규칙은 명세서에 없다.
	3. 표·차트(state['tables'])마다 표·차트 청크를 1개씩 만든다
	   - section_no: 표가 있는 쪽이 속한 섹션 번호
	   - chunk_type: 'table' 또는 'chart' (Table.source_type), doc_id: Table.doc_id (report_tables 원본 표와 연결)
	   - text: 아직 요약이 없으므로 PENDING_TABLE_TEXT를 넣어 두고, summarize_tables 노드가 '캡션+요약'으로 바꾼다
	4. chunk_no는 보고서 안에서 0부터 차례로 붙인다 (텍스트 청크 → 표·차트 청크 순)
	"""
	from hri.config.settings import load_settings
	from hri.splitter.text_splitter import split_sections, split_text

	settings = load_settings()
	sections = split_sections(state.get("pages") or [])
	chunks: list[Chunk] = []

	# 2) 섹션별 텍스트 청크
	for section in sections:
		for piece in split_text(section.text, settings.chunk_size, settings.chunk_overlap):
			chunks.append(Chunk(chunk_no=len(chunks), section_no=section.section_no, page=section.start_page, chunk_type="text", text=piece))

	# 3) 표·차트 청크
	tables: list[Table] = state.get("tables") or []
	warnings: list[str] = []
	if tables and not sections:
		warnings.append(NO_SECTION_WARNING)
	elif tables:
		for table in tables:
			chunks.append(Chunk(
				chunk_no=len(chunks),
				section_no=_section_no_for_page(sections, table.page),
				page=table.page,
				chunk_type=table.source_type,
				text=PENDING_TABLE_TEXT,
				doc_id=table.doc_id,
			))

	update = {"sections": sections, "chunks": chunks}
	if warnings:
		update["warnings"] = warnings     # warnings는 operator.add 리듀서라 다른 노드 경고와 합쳐진다
	return update


def _caption_and_summary(table: Table) -> str:
	"""표·차트 청크의 검색용 글을 만든다: '캡션(줄바꿈)요약' (명세서: '캡션+요약').

	캡션이 없으면 요약만 쓴다. TODO(확인 필요): 요약까지 없으면(요약 실패) 원본 마크다운을 쓴다. 명세서에 규칙이 없다.
	"""
	parts = [p for p in (table.caption, table.summary) if p]
	if not table.summary and table.markdown:
		parts.append(table.markdown)
	return "\n".join(parts) or PENDING_TABLE_TEXT


def summarize_tables_node(state: IngestState) -> dict:
	"""[표·차트 요약 노드] 표·차트마다 검색용 요약을 만들고, 표·차트 청크의 글을 '캡션+요약'으로 바꾼다.

	- summarize_tables(state['tables']) : Table.summary(1~2문장)를 채운 표 목록을 돌려준다 (엄정현 table_loader, LLM 사용)
	  DB 트랜잭션(persist) 밖에서 실행해, LLM이 느려도 DB 연결을 붙잡지 않게 한다 (명세서).
	- 표·차트 청크는 doc_id로 같은 표를 찾아 text를 '캡션+요약'으로 바꾼다. 텍스트 청크는 그대로 둔다.
	- 돌려주는 키는 'summarized_tables'와 'chunks'다.
	  'tables'로 돌려주면 operator.add 리듀서 때문에 같은 표가 두 번 쌓이므로 다른 키에 담는다.
	- 표·차트가 0개면 LLM을 부르지 않고 그대로 통과한다 ({'summarized_tables': []}).
	"""
	tables: list[Table] = state.get("tables") or []
	if not tables:
		return {"summarized_tables": []}

	from hri.loader.table_loader import summarize_tables

	summarized = summarize_tables(tables)
	by_doc_id = {table.doc_id: table for table in summarized}
	chunks = [
		chunk.model_copy(update={"text": _caption_and_summary(by_doc_id[chunk.doc_id])})
		if chunk.doc_id in by_doc_id else chunk
		for chunk in state.get("chunks") or []
	]
	return {"summarized_tables": summarized, "chunks": chunks}


def _page_count(state: IngestState) -> int:
	"""reports.page_count(PDF 전체 쪽 수)에 넣을 값.

	TODO(확인 필요): 쪽 번호는 원본 PDF 기준(1부터)이고 find_body_start()가 앞쪽(표지·목차)만 빼므로
	가장 큰 쪽 번호를 전체 쪽 수로 쓴다. 전체 쪽 수를 따로 넘기는 키는 IngestState에 없다.
	"""
	pages = state.get("pages") or []
	return max((page.page for page in pages), default=0)


def persist_node(state: IngestState) -> dict:
	"""[저장 노드] 보고서·섹션·표·청크를 MySQL에, 청크 벡터를 Chroma에 한 번에 저장한다. {'report_id', 'counts'}를 돌려준다.

	순서 (명세서 persist_node 행, 하나의 DB 연결 = 하나의 트랜잭션)
	1. insert_report(conn, Report)            : reports에 1줄 → report_id (AUTO_INCREMENT)를 받는다 (김희진 report_dao)
	   - 제목·발행기관·발행일은 state['meta'](extract_report_meta 결과), 파일 경로·업로드한 사람은 입력값
	2. insert_sections(conn, report_id, sections)
	3. insert_tables(conn, report_id, summarized_tables)  : 표가 먼저 들어가야 청크의 doc_id(외래 키)가 맞는다 (엄정현 report_dao)
	4. insert_chunks(conn, report_id, chunks)
	5. add_chunks(chunks)                     : 청크를 임베딩해 Chroma에 저장 (김희진 chroma_store, report_id를 채운 청크)
	6. conn.commit()                          : 여기까지 모두 성공했을 때만 DB에 확정한다

	중간에 하나라도 실패하면 (명세서)
	- conn.rollback()으로 DB에 넣은 것을 모두 되돌리고
	- report_id를 이미 받았다면 delete_report_vectors(report_id)로 Chroma에 들어간 벡터도 지운다
	  (Chroma는 DB 트랜잭션에 묶이지 않아 rollback으로 지워지지 않음)
	- 그리고 원래 예외를 다시 던진다 → upload_report()가 잡아 화면에 '업로드 처리 중 오류'를 보여 준다
	LLM은 부르지 않는다.
	"""
	from hri.dao.db import get_connection
	from hri.dao.report_dao import insert_chunks, insert_report, insert_sections, insert_tables
	from hri.vector_store.chroma_store import add_chunks, delete_report_vectors

	meta = state.get("meta") or {}
	sections: list[Section] = state.get("sections") or []
	tables: list[Table] = state.get("summarized_tables") or []
	chunks: list[Chunk] = state.get("chunks") or []

	report = Report(
		title=meta["title"],
		publisher=meta.get("publisher"),
		published_date=meta.get("published_date"),
		page_count=_page_count(state),
		file_path=state["file_path"],
		uploaded_by=state["user_id"],
	)

	report_id = None
	with get_connection() as conn:
		try:
			report_id = insert_report(conn, report)
			insert_sections(conn, report_id, sections)
			insert_tables(conn, report_id, tables)
			insert_chunks(conn, report_id, chunks)
			# Chroma 저장에는 report_id가 들어간 청크가 필요하다 (id = '{report_id}-{chunk_no}')
			add_chunks([chunk.model_copy(update={"report_id": report_id}) for chunk in chunks])
			conn.commit()
		except Exception:
			conn.rollback()
			if report_id is not None:
				try:
					delete_report_vectors(report_id)
				except Exception:
					# 벡터 정리까지 실패해도 원래 오류를 알리는 것이 우선이므로 기록만 남긴다
					logger.exception("보고서 %s 벡터 정리 실패 (Chroma에서 직접 지워야 함)", report_id)
			raise

	# 청크 종류별 개수 (업로드 결과 화면: 텍스트/표/차트 청크 수)
	kinds = Counter(chunk.chunk_type for chunk in chunks)
	counts = {"text": kinds["text"], "table": kinds["table"], "chart": kinds["chart"]}
	return {"report_id": report_id, "counts": counts}


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
