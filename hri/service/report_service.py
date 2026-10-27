"""보고서 목록·본문 · search_reports, get_report_text (장유빈)"""
from hri.dao.report_dao import select_reports
from hri.domain.schemas.report import Report


def search_reports(keyword: str = "", limit: int | None = None) -> list[Report]:
	"""제목·발행기관 키워드로 보고서를 검색해 발행일 최신순으로 돌려준다.

	keyword가 ''이면 전체를, limit이 있으면 상위 limit개만 돌려준다.
	"""
	reports = select_reports(keyword.strip())
	return reports[:limit] if limit is not None else reports