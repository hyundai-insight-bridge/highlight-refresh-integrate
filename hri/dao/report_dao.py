"""보고서 저장·조회 · insert_report, insert_sections, insert_chunks, select_sections, select_summary_json, update_summary_json, get_context_docs (김희진) / insert_tables (엄정현) / select_reports (장유빈)"""
import json
from hri.dao.db import get_connection
from hri.domain.schemas import Chunk, ContextDoc, Report, ReportSummary, Section
from hri.config.settings import load_settings
from pymysql.connections import Connection
from pydantic import ValidationError

# -- select_reports (장유빈)
def _escape_like(text: str) -> str:
	"""LIKE 검색에서 특별한 뜻을 가진 문자(\\, %, _)를 일반 글자로 바꾼다."""
	return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def select_reports(keyword: str) -> list[Report]:
	"""제목 또는 발행기관에 keyword가 들어 있는 보고서를 발행일 최신순으로 조회한다.

	reports와 chunks를 LEFT JOIN해 보고서별 청크 수(chunk_count)를 센다.
	청크가 아직 없는 보고서도 목록에 포함되고, keyword가 ''이면 전체를 조회한다.
	"""
	pattern = f"%{_escape_like(keyword)}%"
	sql = """
		SELECT r.report_id, r.title, r.publisher, r.published_date, r.page_count,
		       r.file_path, r.uploaded_by, COUNT(c.chunk_no) AS chunk_count
		FROM reports r
		LEFT JOIN chunks c ON c.report_id = r.report_id
		WHERE r.title LIKE %s OR r.publisher LIKE %s
		GROUP BY r.report_id
		ORDER BY r.published_date DESC, r.report_id DESC
	"""
	with get_connection() as conn:
		with conn.cursor() as cur:
			cur.execute(sql, (pattern, pattern))
			rows = cur.fetchall()
	return [Report(**row) for row in rows]

# insert_report, insert_sections, insert_chunks (김희진)
def insert_report(conn: Connection, report: Report) -> int:
	"""
	reports 테이블에 보고서 1건을 INSERT하고 새로 생긴 report_id를 돌려준다.
	
	persist_node가 연 커넥션을 받아 쓴다. commit, rollback은 호출부가 한다.
	chunk_count는 DB 칸이 없어 저장하지 않는다. summary_json은 요약 후 update_summary_json()으로 채운다.
	"""
	sql = (
		"INSERT INTO reports (title, publisher, published_date, page_count, file_path, file_hash, uploaded_by) "
		"VALUES (%s, %s, %s, %s, %s, %s, %s)"
	)
	params = (
		report.title,
		report.publisher,
		report.published_date,
		report.page_count,
		report.file_path,
		report.file_hash,
		report.uploaded_by,
	)
	with conn.cursor() as cur:
		cur.execute(sql, params)
		return cur.lastrowid

def insert_sections(conn: Connection, report_id: int, sections: list[Section]) -> int:
	"""
	sections 테이블에 부모 섹션을 executemany()로 한 번에 INSERT하고 넣은 개수를 돌려준다.
	split 단계의 Section.report_id는 None이므로 인자로 받은 report_id를 쓴다.
	(report_id, section_no)가 겹치면 DB가 IntegrityError를 낸다. 빈 목록이면 0."""
	if not sections:
		return 0
	sql = "INSERT INTO sections (report_id, section_no, title, start_page, end_page, text) VALUES (%s, %s, %s, %s, %s, %s)"
	rows = [(report_id, s.section_no, s.title, s.start_page, s.end_page, s.text) for s in sections]

	with conn.cursor() as cur:
		cur.executemany(sql, rows)
	
	return len(rows)

def insert_chunks(conn: Connection, report_id: int, chunks: list[Chunk]) -> int:
	"""
	chunks 테이블에 청크를 executemany()로 한 번에 INSERT하고 넣은 개수를 돌려준다.
	insert_sections()(section_no FK)와 insert_tables()(doc_id FK) 뒤에 호출해야 한다.
	split 단계의 CHunk.report_id는 None이므로 인자로 받은 report_id를 쓴다.
	텍스트 청크는 doc_id가 None, 표, 차트 청크는 doc_id가 있어야 한다(DB CHECK ch_chunks_doc_id). 빈 목록이면 0.
	"""
	if not chunks:
		return 0
	sql = (
		"INSERT INTO chunks (report_id, chunk_no, section_no, page, chunk_type, category, text, doc_id) "
		"VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
	)
	rows = [(report_id, c.chunk_no, c.section_no, c.page, c.chunk_type, c.category, c.text, c.doc_id) for c in chunks]

	with conn.cursor() as cur:
		cur.executemany(sql, rows)

	return len(rows)

# select_sections, select_summary_json, update_summary_json, get_context_docs (김희진)
def select_sections(report_id: int) -> list[Section]:
	"""
	report_id 보고서의 섹션을 section_no 순으로 조회한다.
	summary_graph의 load_sections 노드와 get_report_text()가 사용한다. 섹션이 없으면 빈 목록.
	"""
	sql = (
		"SELECT report_id, section_no, title, start_page, end_page, text " \
		"FROM sections WHERE report_id = %s ORDER BY section_no"
	)
	with get_connection() as conn:
		with conn.cursor() as cur:
			cur.execute(sql, (report_id,))
			rows = cur.fetchall()

	return [Section(**row) for row in rows]

def select_summary_json(report_id: int) -> ReportSummary | None:
	"""
	reports.summary_json(요약 캐시)을 읽어 ReportSummary로 돌려준다.
	summary_graph의 load_cache 노드가 사용한다. 캐시가 없거나 스키마가 바뀌어 읽을 수 없으면 None을 돌려줘 요약을 새로 만들게 한다.
	"""
	with get_connection() as conn:
		with conn.cursor() as cur:
			cur.execute(
				"SELECT summary_json FROM reports WHERE report_id = %s",
				(report_id,))
			row = cur.fetchone()

	if row is None or row["summary_json"] is None:
		return None
	raw = row["summary_json"]

	try:
		if isinstance(raw, (str, bytes)):
			return ReportSummary.model_validate_json(raw)
		return ReportSummary.model_validate(raw) # 드라이버가 이미 dict로 풀어 준 경우
	except (ValidationError, json.JSONDecodeError):
		return None

def update_summary_json(report_id: int, summary: ReportSummary) -> int:
	"""
	ReportSummary를 reports.summary_json(JSON)에 저장하고 바뀐 행 수를 돌려준다.
	summary_graph의 save 노드가 사용한다.
	자체 커넥션으로 commit까지 한다. 없는 report_id면 0을 반환.
	"""
	with get_connection() as conn:
		with conn.cursor() as cur:
			cur.execute(
				"UPDATE reports SET summary_json = %s WHERE report_id = %s",
				(summary.model_dump_json(), report_id),
			)
			updated = cur.rowcount
		conn.commit()
	
	return updated

def _placeholders(count: int, width: int = 1) -> str:
	"""
	IN 절용 자리표시자. (3) -> '%s, %s, %s' / (2, 2) -> '(%s, %s), (%s, %s)'"""
	one = "%s" if width == 1 else "(" + ", ".join(["%s" * width]) + ")"
	return ", ".join([one] * count)

def get_context_docs(chunks: list[Chunk]) -> list[ContextDoc]:
	"""
	검색된 청크를 답변용 ContextDoc으로 바꾼다. 입력 순서(관련도 순)을 그대로 유지한다.
	- 텍스트 청크: (report_id, section_no)의 부모 섹션 원문. 같은 섹션은 1번만, 섹션당 MAX_CONTEXT_CHARS 상한
	- 표, 차트 청크: doc_id로 report_tables의 원본 마크다운, 캡션, needs_review. 같은 doc_id는 1번만
	- 보고서명은 reports에서 조회 원본을 찾지 못한 청크(삭제 등)는 건너뛴다.
	generate 노드가 사용한다.
	"""
	if not chunks:
		return []
	max_chars = load_settings().max_context_chars
	report_ids = list(dict.fromkeys(c.report_id for c in chunks))
	section_keys = list(dict.fromkeys((c.report_id, c.section_no) for c in chunks if c.chunk_type == "text"))
	doc_ids = list(dict.fromkeys(c.doc_id for c in chunks if c.chunk_type != "text" and c.doc_id))

	with get_connection() as conn:
		with conn.cursor() as cur:
			cur.execute(
				f"SELECT report_id, title FROM reports WHERE report_id in ({_placeholders(len(report_ids))})",
				report_ids,
			)
			titles = {
				row["report_id"]: row["title"] for row in cur.fetchall()}
			sections = {}

			if section_keys:
				params = [value for key in section_keys for value in key]
				cur.execute(
					"SELECT report_id, section_no, title, start_page, end_page, text FROM sections" \
					f"WHERE (report_id, section_no) IN ({_placeholders(len(section_keys), 2)})",
					params,
				)
				sections = {(row["report_id"], row["section_no"]): row for row in cur.fetchall()}

			tables = {}
			if doc_ids:
				cur.execute(
					"SELECT doc_id, page, caption, markdown, needs_review FROM report_tables " \
					f"WHERE doc_id IN ({_placeholders(len(doc_ids))})",
					doc_ids,
				)
				tables = {row["doc_id"]: row for row in cur.fetchall()}

	docs: list[ContextDoc] = []
	seen_sections: set[tuple[int, int]] = set()
	seen_doc_ids: set[str] = set()

	for chunk in chunks:
		report_title = titles.get(chunk.report_id)

		if report_title is None:
			continue
		if chunk.chunk_type == "text":
			key = (chunk.report_id, chunk.section_no)
			section = sections.get(key)
			if section is None or key in seen_sections:
				continue
			seen_sections.add(key)
			text = section["text"] if max_chars is None else section["text"][:max_chars]
			docs.append(ContextDoc(
				report_id=chunk.report_id,
				report_title=report_title,
				kind="text",
				section_title=section["title"],
				page_start=section["start_page"],
				page_end=section["end_page"],
				text=text
			))
		else:
			table = tables.get(chunk.doc_id)
			if table is None or chunk.doc_id in seen_doc_ids:
				continue
			seen_doc_ids.add(chunk.doc_id)
			docs.append(ContextDoc(
				report_id=chunk.report_id,
				report_title=report_title,
				kind=chunk.chunk_type,
				caption=table["caption"],
				page_start=table["page"],
				page_end=table["page"],
				text=table["markdown"],
				needs_review=bool(table["needs_review"]),
			))
	return docs