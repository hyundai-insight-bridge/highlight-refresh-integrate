"""format_docs 출력 형식 테스트 (장유빈)"""
from hri.domain.schemas.qa import ContextDoc
from hri.prompt.rag_prompt import format_docs


def _doc(**kwargs) -> ContextDoc:
	base = dict(
		report_id=1, report_title="2026 경제전망", kind="text", section_title="물가",
		caption=None, page_start=12, page_end=13, text="본문입니다", needs_review=False,
	)
	base.update(kwargs)
	return ContextDoc(**base)


def test_text_doc():
	assert format_docs([_doc()]) == "[출처: 2026 경제전망 p.12-13 / 물가]\n본문입니다"


def test_no_section_title():
	assert format_docs([_doc(section_title=None)]) == "[출처: 2026 경제전망 p.12-13]\n본문입니다"


def test_chart_doc():
	doc = _doc(kind="chart", caption="그림 3", page_start=20, page_end=20)
	assert format_docs([doc]) == "[출처: 2026 경제전망 p.20 / 그림 3 (차트 OCR)]\n본문입니다"


def test_needs_review():
	doc = _doc(kind="chart", caption="그림 3", page_start=20, page_end=20, needs_review=True)
	assert format_docs([doc]).startswith("[출처: 2026 경제전망 p.20 / 그림 3 (차트 OCR)] (추정값)\n")


def test_multiple_and_empty():
	text = format_docs([_doc(text="A"), _doc(text="B")])
	assert text == "[출처: 2026 경제전망 p.12-13 / 물가]\nA\n\n[출처: 2026 경제전망 p.12-13 / 물가]\nB"
	assert format_docs([]) == ""