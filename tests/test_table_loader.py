"""table_to_markdown()·split_big_table()가 명세대로 동작하는지 확인하는 테스트 (네트워크·DB·.env 없이 실행).

표 rows는 pdfplumber extract_tables()가 HRI 보고서에서 돌려주는 모양을 줄여서 흉내 낸다
(병합된 칸·빈 칸은 None, 칸 안 줄바꿈은 '\n').
"""

import pytest

import hri.loader.table_loader as table_loader
from hri.domain.schemas import Table
from hri.graph.ingest_graph import extract_tables_node
from hri.loader.table_loader import split_big_table, table_to_markdown


# 머리글 1행 + 본문 body_rows행 표. 본문 i행은 ['2000+i', 'i.0']
def make_rows(body_rows):
	return [["연도", "물가상승률"]] + [[str(2000 + i), f"{i}.0"] for i in range(body_rows)]


# 마크다운 표 한 줄의 칸 수 ('\|'는 글자라서 세지 않음)
def count_cells(line):
	return line.replace("\\|", "").count("|") - 1


# ---------------------------------------------------------------------
# table_to_markdown()
# ---------------------------------------------------------------------
# [확인 1] 머리글 → 구분선(|---|) → 본문 순서
def test_table_to_markdown_order():
	rows = [["구 분", "2025", "2026(E)"], ["경제성장률 (%)", "1.1", "3.5"], ["민간소비 (%)", "1.5", "2.4"]]
	assert table_to_markdown(rows) == (
		"| 구 분 | 2025 | 2026(E) |\n"
		"|---|---|---|\n"
		"| 경제성장률 (%) | 1.1 | 3.5 |\n"
		"| 민간소비 (%) | 1.5 | 2.4 |"
	)


# [확인 2] None(병합된 칸·빈 칸)은 빈칸, 칸 수는 그대로
def test_table_to_markdown_none_is_blank():
	rows = [["구 분", None, "2025"], [None, "민간소비 (%)", "1.5"]]
	lines = table_to_markdown(rows).split("\n")
	assert lines[0] == "| 구 분 |  | 2025 |"
	assert lines[2] == "|  | 민간소비 (%) | 1.5 |"
	assert "None" not in "\n".join(lines)


# [확인 3] 칸 안의 줄바꿈·연속 공백은 공백 1칸으로 (표 한 행이 마크다운 한 줄로 유지됨)
def test_table_to_markdown_newline_in_cell():
	rows = [["구분", "내용"], ["1. 포퓰리즘(populism)\n의 시대", "경제\n및  사회 환경의 급변 "]]
	lines = table_to_markdown(rows).split("\n")
	assert len(lines) == 3
	assert lines[2] == "| 1. 포퓰리즘(populism) 의 시대 | 경제 및 사회 환경의 급변 |"


# [확인 4] 칸 안의 '|'는 '\|'로 바꿔 칸이 늘어나지 않게
def test_table_to_markdown_pipe_in_cell():
	rows = [["구분", "값"], ["A|B", "1"]]
	lines = table_to_markdown(rows).split("\n")
	assert lines[2] == "| A\\|B | 1 |"
	assert {count_cells(line) for line in (lines[0], lines[2])} == {2}


# [확인 5] 숫자를 넘겨도 글자로 바꿔 표를 만든다 (비교표·대시보드에서 쓸 때)
def test_table_to_markdown_number_cells():
	assert table_to_markdown([["지표", "값"], ["성장률", 2.4], ["건수", 7]]).split("\n")[2:] == ["| 성장률 | 2.4 |", "| 건수 | 7 |"]


# [확인 6] 빈 rows → "", 머리글만 있으면 머리글 + 구분선
def test_table_to_markdown_empty_and_header_only():
	assert table_to_markdown([]) == ""
	assert table_to_markdown([["연도", "물가상승률"]]) == "| 연도 | 물가상승률 |\n|---|---|"


# ---------------------------------------------------------------------
# split_big_table()
# ---------------------------------------------------------------------
# [확인 7] 본문 23행 → 10·10·3행 3조각, 모든 조각 첫 줄이 머리글, 본문 순서·내용은 그대로
def test_split_big_table_pieces():
	rows = make_rows(23)
	pieces = split_big_table(rows)
	assert [len(p) for p in pieces] == [11, 11, 4]
	assert all(p[0] == ["연도", "물가상승률"] for p in pieces)
	assert [row for p in pieces for row in p[1:]] == rows[1:]


# [확인 8] 경계: 본문 10행은 나누지 않고, 11행부터 나눈다 (기준은 머리글을 뺀 본문 행 수)
@pytest.mark.parametrize("body_rows, sizes", [(0, [1]), (3, [4]), (10, [11]), (11, [11, 2])])
def test_split_big_table_boundary(body_rows, sizes):
	rows = make_rows(body_rows)
	pieces = split_big_table(rows)
	assert [len(p) for p in pieces] == sizes
	if len(pieces) == 1:
		assert pieces == [rows]


# [확인 9] max_rows를 바꾸면 그 행 수로 나눈다
def test_split_big_table_max_rows():
	pieces = split_big_table(make_rows(5), max_rows=2)
	assert [[row[0] for row in p] for p in pieces] == [["연도", "2000", "2001"], ["연도", "2002", "2003"], ["연도", "2004"]]


# [확인 10] 빈 rows → [], max_rows가 1보다 작으면 ValueError (표가 사라지지 않게)
def test_split_big_table_empty_and_bad_max_rows():
	assert split_big_table([]) == []
	for bad in (0, -1):
		with pytest.raises(ValueError):
			split_big_table(make_rows(3), max_rows=bad)


# ---------------------------------------------------------------------
# 두 함수를 이어서: 잘린 조각에도 머리글이 붙어 나오는지
# ---------------------------------------------------------------------
# HRI 보고서 '세계 경제 전망' 표 모양 (머리글 1행 + 본문 14행, 병합 칸은 None)
WORLD_TABLE = [["구 분", None, "2024", "2025", "2026(E)", "2027(E)"]] + [
	["세계 경제성장률" if i == 0 else None, f"국가{i}", "3.5", "3.5", "3.0", "3.4"] for i in range(14)
]


# [확인 11] 조각마다 table_to_markdown() → 모든 조각이 '머리글 줄 + 구분선'으로 시작하고, 줄마다 칸 수가 같다
def test_split_then_markdown_keeps_header():
	header_line = "| 구 분 |  | 2024 | 2025 | 2026(E) | 2027(E) |"
	markdowns = [table_to_markdown(p) for p in split_big_table(WORLD_TABLE)]
	assert len(markdowns) == 2
	for md in markdowns:
		lines = md.split("\n")
		assert lines[0] == header_line
		assert lines[1] == "|---|---|---|---|---|---|"
		assert {count_cells(line) for line in lines if line != lines[1]} == {6}
	assert "| 세계 경제성장률 | 국가0 |" in markdowns[0]
	assert "| 세계 경제성장률" not in markdowns[1]


# [확인 12] 표 노드(extract_tables_node)에 진짜 두 함수를 연결: 큰 표는 '(1/2)'·'(2/2)' 조각마다 머리글이 있는 마크다운
#           extract_tables·validate_table은 아직 레포에 없어서(3.2.10) 이 테스트에서만 가짜로 넣는다
def test_extract_tables_node_with_real_functions(monkeypatch):
	big = Table(page=12, caption="< 세계 경제 전망 >", rows=[["" if c is None else c for c in r] for r in WORLD_TABLE])
	small = Table(page=3, caption="[표 1]", rows=make_rows(2))
	monkeypatch.setattr(table_loader, "extract_tables", lambda file_path: [small, big], raising=False)
	monkeypatch.setattr(table_loader, "validate_table", lambda rows: "✅ 이상 없음", raising=False)

	tables = extract_tables_node({"file_path": "report.pdf"})["tables"]

	assert [t.caption for t in tables] == ["[표 1]", "< 세계 경제 전망 > (1/2)", "< 세계 경제 전망 > (2/2)"]
	assert [len(t.rows) for t in tables] == [3, 11, 5]
	assert tables[0].markdown == table_to_markdown(make_rows(2))
	assert all(t.markdown.startswith("| 구 분 |  | 2024 | 2025 | 2026(E) | 2027(E) |\n|---|") for t in tables[1:])


# ---------------------------------------------------------------------
# [추가 기능 · 명세서 밖] split_big_table(header_rows=...): 머리글이 2줄 이상인 표
# ---------------------------------------------------------------------
# HRI '경제 전망' 표 모양 (머리글 2줄 + 본문 12행). 1줄은 연도, 2줄은 상반·하반·연간 (병합 칸은 빈칸)
OUTLOOK_HEADER = [
	["구 분", "", "2025", "2026", "", "", "2027(E)", "", ""],
	["", "", "", "상반", "하반(E)", "연간(E)", "상반", "하반", "연간"],
]
OUTLOOK_TABLE = OUTLOOK_HEADER + [[f"지표{i}", "", "1.1", "3.8", "3.2", "3.5", "2.2", "2.5", "2.4"] for i in range(12)]


# [확인 13] header_rows=2: 모든 조각 앞에 머리글 2줄이 붙고, 본문은 머리글 2줄을 뺀 12행을 10·2행으로 나눈다
def test_split_big_table_two_header_rows():
	pieces = split_big_table(OUTLOOK_TABLE, header_rows=2)
	assert [len(p) for p in pieces] == [12, 4]
	assert all(p[:2] == OUTLOOK_HEADER for p in pieces)
	assert [row for p in pieces for row in p[2:]] == OUTLOOK_TABLE[2:]
	# 마크다운으로 바꾸면 둘째 조각에도 '상반 | 하반(E) | 연간(E)' 줄이 남는다 (마크다운 머리글은 1줄이라 2줄째는 구분선 아래 첫 줄)
	lines = table_to_markdown(pieces[1]).split("\n")
	assert lines[2] == "|  |  |  | 상반 | 하반(E) | 연간(E) | 상반 | 하반 | 연간 |"


# [확인 14] 기본값(header_rows=1)은 명세서대로 첫 줄만 붙인다 → 같은 표의 둘째 조각에는 '상반·하반' 줄이 없다 (추가 기능을 둔 이유)
def test_split_big_table_default_is_one_header_row():
	pieces = split_big_table(OUTLOOK_TABLE)
	assert split_big_table(OUTLOOK_TABLE, header_rows=1) == pieces
	assert [len(p) for p in pieces] == [11, 4]
	assert pieces[1][0] == OUTLOOK_HEADER[0] and OUTLOOK_HEADER[1] not in pieces[1]


# [확인 15] header_rows도 본문 행 수 경계에 들어간다 (머리글 2줄 + 본문 10행은 나누지 않음), 1보다 작으면 ValueError
def test_split_big_table_header_rows_boundary_and_bad_value():
	table = OUTLOOK_TABLE[:12]
	assert split_big_table(table, header_rows=2) == [table]
	for bad in (0, -1):
		with pytest.raises(ValueError):
			split_big_table(OUTLOOK_TABLE, header_rows=bad)
