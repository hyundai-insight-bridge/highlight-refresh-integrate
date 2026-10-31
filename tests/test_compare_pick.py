"""보고서 선택 창 테스트 · 목록·선택 칸·페이지 넘김·최대 선택 수 (장유빈)"""
from hri.view import indicator_view
from hri.view.indicator_view import (
	MAX_COMPARE_REPORTS,
	PICK_PAGE_SIZE,
	load_compare_reports,
	new_pick,
	on_pick_change,
	on_pick_page,
	reset_compare_reports,
)


class _R:
	def __init__(self, report_id, title):
		self.report_id, self.title = report_id, title


def _use_reports(monkeypatch, count: int):
	"""보고서 목록을 가짜 count개로 바꾸고 search_reports가 받은 user_id를 기록한다."""
	seen = []

	def fake_search(keyword="", limit=None, user_id=None):
		seen.append(user_id)
		return [_R(i, f"보고서{i}") for i in range(1, count + 1)]

	monkeypatch.setattr(indicator_view, "search_reports", fake_search)
	return seen


USER = {"user": {"user_id": "kim", "role": "user"}}


def test_first_page_shows_page_size_reports(monkeypatch):
	_use_reports(monkeypatch, 23)
	pick, checkbox, page, prev_btn, next_btn = reset_compare_reports(USER)
	assert [rid for _, rid in checkbox["choices"]] == list(range(1, PICK_PAGE_SIZE + 1))
	assert page == "1 / 3"
	assert prev_btn["interactive"] is False and next_btn["interactive"] is True


def test_normal_user_sees_only_own_reports(monkeypatch):
	seen = _use_reports(monkeypatch, 3)
	reset_compare_reports(USER)
	assert seen == ["kim"]


def test_next_and_prev_page(monkeypatch):
	_use_reports(monkeypatch, 23)
	pick = reset_compare_reports(USER)[0]
	pick, checkbox, page, prev_btn, next_btn = on_pick_page(on_pick_page(pick, 1)[0], 1)
	assert [rid for _, rid in checkbox["choices"]] == [21, 22, 23]
	assert page == "3 / 3" and next_btn["interactive"] is False
	assert on_pick_page(pick, 5)[2] == "3 / 3"  # 마지막 페이지를 넘지 않는다


def test_selection_is_kept_across_pages(monkeypatch):
	_use_reports(monkeypatch, 23)
	pick = on_pick_change([1, 2], reset_compare_reports(USER)[0])[0]
	pick = on_pick_page(pick, 1)[0]
	pick, checkbox, *_ = on_pick_change([11], pick)
	assert pick["selected"] == [1, 2, 11]
	assert checkbox["value"] == [11]
	assert checkbox["label"].endswith(f"(선택 3/{MAX_COMPARE_REPORTS})")


def test_uncheck_on_page_removes_only_that_report(monkeypatch):
	_use_reports(monkeypatch, 23)
	pick = on_pick_change([1, 2], reset_compare_reports(USER)[0])[0]
	pick = on_pick_change([2], pick)[0]
	assert pick["selected"] == [2]


def test_more_than_max_is_rejected_and_rest_disabled(monkeypatch):
	_use_reports(monkeypatch, 23)
	pick, checkbox, *_ = on_pick_change([1, 2, 3, 4, 5], reset_compare_reports(USER)[0])
	assert "limit-reached" in checkbox["elem_classes"]
	pick, checkbox, *_ = on_pick_change([1, 2, 3, 4, 5, 6], pick)
	assert pick["selected"] == [1, 2, 3, 4, 5]
	assert checkbox["value"] == [1, 2, 3, 4, 5]


def test_reload_keeps_selection_still_in_list(monkeypatch):
	_use_reports(monkeypatch, 5)
	pick = on_pick_change([4, 5], reset_compare_reports(USER)[0])[0]
	_use_reports(monkeypatch, 4)  # 보고서 5가 사라짐
	pick = load_compare_reports(USER, pick)[0]
	assert pick["selected"] == [4]


def test_list_error_shows_empty_list(monkeypatch):
	def broken(*a, **k):
		raise RuntimeError("DB 오류")

	monkeypatch.setattr(indicator_view, "search_reports", broken)
	pick, checkbox, page, *_ = load_compare_reports(USER, new_pick())
	assert checkbox["choices"] == [] and page == "1 / 1"
