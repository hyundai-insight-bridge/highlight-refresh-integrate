"""보고서 저장·조회 · insert_report, insert_sections, insert_chunks, select_sections, update_summary_json, get_context_docs (김희진) / insert_tables (엄정현) / select_reports (장유빈)"""
from hri.dao.db import get_connection
from hri.domain.schemas.report import Report, Chunk, Section
from pymysql.connections import Connection

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
		"INSERT INTO reports (title, publisher, published_date, page_count, file_path, file_hash, uploaded_by) " \
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

def insert_section(conn: Connection, report_id: int, sections: list[Section]) -> int:
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
	텍스트 청크는 doc_id가 None, 표, 차트 청크는 doc_id가 있어야 한다(DB CHECK ch_chunks_doc_id). 빈 목록이면 0."""
	if not chunks:
		return 0
	sql = (
		"INSERT INTO chunks (report_id, chunk_no, section_no, page, chunk_type, category, text, doc_id) " \
		"VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
	)
	rows = [(report_id, c.chunk_no, c.section_no, c.page, c.chunk_type, c.category, c.text, c.doc_id) for c in chunks]

	with conn.cursor() as cur:
		cur.executemany(sql, rows)

	return len(rows)