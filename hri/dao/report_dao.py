"""보고서 저장·조회 · insert_report, insert_sections, insert_chunks, select_sections, update_summary_json, get_context_docs (김희진) / insert_tables (엄정현) / select_reports (장유빈)"""
from hri.dao.db import get_connection
from hri.domain.schemas.report import Report


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