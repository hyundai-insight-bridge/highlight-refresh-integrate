"""지표 비교표·차트 로직 테스트 · 가짜 지표·보고서 목록 사용 (장유빈)"""
from pathlib import Path

import pytest

from hri.domain.schemas import Indicator
from hri.service import indicator_service
from hri.service.indicator_service import build_compare_table, plot_indicators


class _R:
	def __init__(self, report_id, title):
		self.report_id, self.title = report_id, title


def _ind(name="경제성장률", value=2.0, unit="%", period="2027", needs_review=False) -> Indicator:
	return Indicator(name=name, value=value, unit=unit, period=period, source="text", needs_review=needs_review)


def _use(monkeypatch, by_report: dict, titles: dict | None = None, plot_dir: Path | None = None):
	"""지표 추출·보고서 목록을 가짜로 바꾼다. by_report는 {report_id: [Indicator, ...]}."""
	titles = titles if titles is not None else {rid: f"보고서{rid}" for rid in by_report}
	monkeypatch.setattr(indicator_service, "extract_indicators", lambda rid: by_report.get(rid, []))
	monkeypatch.setattr(indicator_service, "search_reports", lambda keyword="": [_R(rid, t) for rid, t in titles.items()])
	if plot_dir is not None:
		monkeypatch.setattr(indicator_service, "PLOT_DIR", plot_dir)


def _lines(table: str) -> list[str]:
	return table.splitlines()


# ---------------- build_compare_table ----------------
def test_table_pivots_by_name_period_unit(monkeypatch):
	_use(monkeypatch, {1: [_ind(value=2.0)], 2: [_ind(value=2.4)]}, {1: "A", 2: "B"})
	assert _lines(build_compare_table([1, 2])) == [
		"| 지표 | 시점 | 단위 | A | B |",
		"| --- | --- | --- | --- | --- |",
		"| 경제성장률 | 2027 | % | 2 | 2.4 |",
	]


def test_missing_cells_are_dash(monkeypatch):
	_use(monkeypatch, {1: [_ind(), _ind("실업률", 3.1)], 2: [_ind(value=2.4)]}, {1: "A", 2: "B"})
	lines = _lines(build_compare_table([1, 2]))
	assert lines[-1] == "| 실업률 | 2027 | % | 3.1 | - |"


def test_shared_rows_come_first(monkeypatch):
	_use(monkeypatch, {1: [_ind("가나다", 1.0), _ind("실업률", 3.1)], 2: [_ind("실업률", 3.3)]}, {1: "A", 2: "B"})
	names = [line.split(" | ")[0].strip("| ") for line in _lines(build_compare_table([1, 2]))[2:]]
	assert names == ["실업률", "가나다"]


def test_needs_review_gets_star_and_note(monkeypatch):
	_use(monkeypatch, {1: [_ind(value=1390.0, unit="원", needs_review=True)], 2: [_ind(value=1380.0, unit="원")]}, {1: "A", 2: "B"})
	table = build_compare_table([1, 2])
	assert "| 1,390* | 1,380 |" in table
	assert table.splitlines()[-1].startswith("*")


def test_no_note_without_review(monkeypatch):
	_use(monkeypatch, {1: [_ind()], 2: [_ind()]})
	assert "*" not in build_compare_table([1, 2])


def test_same_unit_different_period_are_different_rows(monkeypatch):
	_use(monkeypatch, {1: [_ind(period="2027"), _ind(period="2028", value=2.2)], 2: [_ind(period="2027")]})
	body = _lines(build_compare_table([1, 2]))[2:]
	assert [line.split(" | ")[1] for line in body] == ["2027", "2028"]


def test_first_value_wins_when_report_repeats_a_row(monkeypatch):
	_use(monkeypatch, {1: [_ind(value=2.0), _ind(value=2.5)], 2: [_ind()]})
	assert "| 2 | 2 |" in build_compare_table([1, 2])


def test_duplicate_titles_get_report_id(monkeypatch):
	_use(monkeypatch, {1: [_ind()], 2: [_ind()]}, {1: "같은 제목", 2: "같은 제목"})
	assert _lines(build_compare_table([1, 2]))[0] == "| 지표 | 시점 | 단위 | 같은 제목 (#1) | 같은 제목 (#2) |"


def test_unknown_report_gets_fallback_title(monkeypatch):
	_use(monkeypatch, {1: [_ind()], 2: [_ind()]}, {1: "A"})
	assert _lines(build_compare_table([1, 2]))[0].endswith("| A | 보고서 #2 |")


def test_pipe_in_title_is_escaped(monkeypatch):
	_use(monkeypatch, {1: [_ind()], 2: [_ind()]}, {1: "A|B", 2: "C"})
	assert "A\\|B" in build_compare_table([1, 2])


def test_duplicate_report_ids_are_merged(monkeypatch):
	_use(monkeypatch, {1: [_ind()]}, {1: "A"})
	assert _lines(build_compare_table([1, 1]))[0] == "| 지표 | 시점 | 단위 | A |"


def test_empty_unit_is_dash(monkeypatch):
	_use(monkeypatch, {1: [_ind(unit="")], 2: [_ind(unit="")]})
	assert "| 경제성장률 | 2027 | - |" in build_compare_table([1, 2])


def test_no_indicators_returns_empty_string(monkeypatch):
	_use(monkeypatch, {})
	assert build_compare_table([1, 2]) == ""


@pytest.mark.parametrize("value, expected", [(1390.0, "1,390"), (2.5, "2.5"), (-0.3, "-0.3"), (0.0, "0"), (1234567.891, "1,234,567.89"), (-0.001, "0")])
def test_format_value(value, expected):
	assert indicator_service._format_value(value) == expected


# ---------------- plot_indicators ----------------
def _png(path: str) -> bytes:
	data = Path(path).read_bytes()
	assert data[:8] == b"\x89PNG\r\n\x1a\n"
	return data


def test_plot_writes_png_with_uuid_name(monkeypatch, tmp_path):
	_use(monkeypatch, {1: [_ind(value=2.0)], 2: [_ind(value=2.4)]}, plot_dir=tmp_path)
	first, second = plot_indicators([1, 2]), plot_indicators([1, 2])
	assert Path(first).parent == tmp_path and Path(first).name.startswith("compare_") and first.endswith(".png")
	assert first != second
	_png(first)


def test_plot_returns_none_without_shared_indicators(monkeypatch, tmp_path):
	_use(monkeypatch, {1: [_ind("가")], 2: [_ind("나")]}, plot_dir=tmp_path)
	assert plot_indicators([1, 2]) is None
	assert list(tmp_path.iterdir()) == []


def test_plot_returns_none_without_any_indicators(monkeypatch, tmp_path):
	_use(monkeypatch, {}, plot_dir=tmp_path)
	assert plot_indicators([1, 2]) is None


def test_plot_handles_units_review_negative_and_many_rows(monkeypatch, tmp_path):
	items1 = [_ind(f"지표{i}", float(i), "%", "2027") for i in range(12)] + [_ind("환율", 1390.0, "원", "2027Q1", needs_review=True), _ind("수지", -5.0, "억 원", "2027")]
	items2 = [_ind(f"지표{i}", float(i) + 0.5, "%", "2027") for i in range(12)] + [_ind("환율", 1380.0, "원", "2027Q1"), _ind("수지", 3.0, "억 원", "2027")]
	_use(monkeypatch, {1: items1, 2: items2, 3: items1[:2]}, plot_dir=tmp_path)
	_png(plot_indicators([1, 2, 3]))


def test_plot_limits_unit_groups(monkeypatch, tmp_path):
	units = ["%", "원", "억 원", "조 원", "%p"]
	by_report = {rid: [_ind(f"지표{u}", 1.0 + rid, u) for u in units] for rid in (1, 2)}
	_use(monkeypatch, by_report, plot_dir=tmp_path)
	_png(plot_indicators([1, 2]))  # 오류 없이 MAX_UNIT_GROUPS개 칸만 그린다


def test_korean_font_comes_from_assets_fonts(monkeypatch, tmp_path):
	fonts = tmp_path / "fonts"
	fonts.mkdir()
	real = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NanumGothic.ttf"
	if not real.exists():
		pytest.skip("assets/fonts에 한글 폰트 파일이 없습니다")
	(fonts / "NanumGothic.ttf").write_bytes(real.read_bytes())
	monkeypatch.setattr(indicator_service, "FONT_DIR", fonts)
	assert indicator_service._use_korean_font() == "NanumGothic"


def test_missing_font_dir_does_not_break(monkeypatch, tmp_path):
	monkeypatch.setattr(indicator_service, "FONT_DIR", tmp_path / "none")
	monkeypatch.setattr(indicator_service, "SYSTEM_FONT_NAMES", ["이런이름의폰트는없다"])
	assert indicator_service._use_korean_font() is None