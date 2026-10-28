"""table_to_markdown()·split_big_table()·extract_tables()·validate_table()이 명세대로 동작하는지 확인하는 테스트
(네트워크·DB·.env 없이 실행).

- 3.2.7  table_to_markdown()·split_big_table()           : [확인 1]~[확인 15]
- 3.2.10 extract_tables()·validate_table()·캡션 정규식 : [확인 16]~[확인 24]
  - 표 PDF는 pymupdf로 tmp_path(pytest가 주는 임시 폴더)에 칸 선을 그려서 만든다 (test_pdf_loader와 같은 방식)
  - [확인 24] 실제 HRI 보고서 테스트는 HRI_PDF_DIR(HRI PDF 폴더)이 있을 때만 실행한다 (PDF는 data/raw처럼 레포에 올리지 않음)

표 rows는 pdfplumber extract_tables()가 HRI 보고서에서 돌려주는 모양을 줄여서 흉내 낸다
(병합된 칸 자리는 None, 글자가 없는 칸은 "", 칸 안 줄바꿈은 '\n').
"""

import os
from pathlib import Path

import pdfplumber
import pymupdf
import pytest

import hri.loader.table_loader as table_loader
from hri.domain.schemas import Table
from hri.graph.ingest_graph import TABLE_WARNING, extract_tables_node
from hri.loader.table_loader import (
	CAPTION,
	TABLE_OK,
	extract_tables,
	split_big_table,
	table_to_markdown,
	validate_table,
)


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


# [확인 12] 표 노드(extract_tables_node)에 진짜 함수를 연결: 큰 표는 '(1/2)'·'(2/2)' 조각마다 머리글이 있는 마크다운,
#           병합 칸(None)이 있는 표만 검수 경고가 warnings에 들어간다
#           extract_tables는 PDF가 있어야 해서 이 테스트에서만 가짜로 넣는다 (진짜는 [확인 17]~[확인 21]·[확인 24])
def test_extract_tables_node_with_real_functions(monkeypatch):
	big = Table(page=12, caption="< 세계 경제 전망 >", rows=WORLD_TABLE)
	small = Table(page=3, caption="[표 1]", rows=make_rows(2))
	monkeypatch.setattr(table_loader, "extract_tables", lambda file_path: [small, big])

	result = extract_tables_node({"file_path": "report.pdf"})
	tables = result["tables"]

	assert [t.caption for t in tables] == ["[표 1]", "< 세계 경제 전망 > (1/2)", "< 세계 경제 전망 > (2/2)"]
	assert [len(t.rows) for t in tables] == [3, 11, 5]
	assert tables[0].markdown == table_to_markdown(make_rows(2))
	assert all(t.markdown.startswith("| 구 분 |  | 2024 | 2025 | 2026(E) | 2027(E) |\n|---|") for t in tables[1:])
	assert result["warnings"] == [TABLE_WARNING.format(page=12, caption="< 세계 경제 전망 >", result=validate_table(WORLD_TABLE))]


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


# =====================================================================
# 3.2.10 extract_tables()·validate_table()·캡션 정규식
# =====================================================================
# 표 PDF 만들기: 쪽 크기는 A4(595x842pt). pdfplumber 좌표는 쪽 위가 0이고 아래로 갈수록 커진다
COL_W = 80   # 칸 너비(pt)
ROW_H = 20   # 칸 높이(pt)


def draw_table(page, x, y, rows, merged=()):
	"""(x, y)를 왼쪽 위로 해서 rows를 칸 선이 있는 표로 그린다. 빈 글자("")·None 칸은 글자를 쓰지 않는다.

	merged: 오른쪽 칸과 합칠 칸의 (행, 열) 좌표(0부터). 그 칸 오른쪽 세로선을 그리지 않아서 두 칸이 한 칸이 된다
	"""
	n_rows, n_cols = len(rows), len(rows[0])
	for r in range(n_rows + 1):
		page.draw_line((x, y + r * ROW_H), (x + n_cols * COL_W, y + r * ROW_H))
	for c in range(n_cols + 1):
		for r in range(n_rows):
			if 0 < c < n_cols and (r, c - 1) in merged:
				continue
			page.draw_line((x + c * COL_W, y + r * ROW_H), (x + c * COL_W, y + (r + 1) * ROW_H))
	for r, row in enumerate(rows):
		for c, text in enumerate(row):
			if text:
				page.insert_text((x + c * COL_W + 4, y + r * ROW_H + 14), text, fontname="korea", fontsize=10)


def write_text(page, x, y, text):
	"""글자 줄 하나를 쓴다. y는 글자 아래 기준선 (글자는 y보다 약 10pt 위까지 차지함)."""
	page.insert_text((x, y), text, fontname="korea", fontsize=10)


def make_pdf(path, pages):
	"""pages: 쪽마다 '그릴 함수(page를 받음)' 목록. None이면 빈 쪽."""
	doc = pymupdf.open()
	for draw in pages:
		page = doc.new_page(width=595, height=842)
		if draw:
			draw(page)
	doc.save(str(path))
	doc.close()
	return str(path)


PRICE_ROWS = [["구분", "2025", "2026(E)"], ["소비자물가", "2.1", "2.0"], ["근원물가", "1.9", "2.1"]]


# ---------------------------------------------------------------------
# 캡션 정규식 CAPTION
# ---------------------------------------------------------------------
# [확인 16] 두 형식을 모두 잡는다: 명세서 '[표 n] 제목'(줄 끝까지)·HRI '< 제목 >'(번호 없음),
#           한 줄에 캡션 두 개(HRI 좌우 배치)면 따로 잡고, 꺾쇠가 비었거나 그림 캡션·두 줄로 나뉜 꺾쇠는 잡지 않는다
#           (알려진 한계) 한 줄 안의 부등호 문장 '1 < 2 이고 3 > 2'는 정규식만으로는 거르지 못한다
#           → extract_tables()는 표 바로 위 30pt 안의 캡션만 쓰므로 본문 문장이 캡션이 되는 경우를 줄인다 ([확인 19])
@pytest.mark.parametrize("line, expected", [
	("[표 1] 주요 지표 전망", ["[표 1] 주요 지표 전망"]),
	("[ 표 12 ]부문별 성장률", ["[ 표 12 ]부문별 성장률"]),
	("< 주요국 경제성장률 전망 >", ["< 주요국 경제성장률 전망 >"]),
	("<IB 국제유가 전망(‘25.2월 평균) >", ["<IB 국제유가 전망(‘25.2월 평균) >"]),
	("< 지역별 주택 매매가격지수 상승률 > < 주택 매매시장 소비심리지수 >",
		["< 지역별 주택 매매가격지수 상승률 >", "< 주택 매매시장 소비심리지수 >"]),
	("[표 1] 물가 [표 2] 고용", ["[표 1] 물가 ", "[표 2] 고용"]),
	("< >", []),
	("금리 1 < 2 이고 3 > 2", ["< 2 이고 3 >"]),
	("[그림 1] 경제성장률 추이", []),
	("표 1. 주요 지표", []),
	("< 세계 주요국 원유 소비량\n(2023년) >", []),
])
def test_caption_pattern(line, expected):
	assert CAPTION.findall(line) == expected


# ---------------------------------------------------------------------
# extract_tables()
# ---------------------------------------------------------------------
# [확인 17] 행·열 구조 그대로(rows), 쪽 번호는 1부터(표가 있는 2·3쪽), 캡션 두 형식 모두, 표가 없는 쪽은 건너뜀
#           markdown은 비워 둔다 (표 노드가 채움)
def test_extract_tables_rows_page_caption(tmp_path):
	def page2(page):
		write_text(page, 72, 92, "[표 1] 물가 전망")
		draw_table(page, 72, 100, PRICE_ROWS)

	def page3(page):
		write_text(page, 72, 192, "< 고용 전망 >")
		draw_table(page, 72, 200, [["구분", "2025"], ["실업률", "2.8"]])

	tables = extract_tables(make_pdf(tmp_path / "a.pdf", [None, page2, page3]))

	assert all(isinstance(t, Table) for t in tables)
	assert [(t.page, t.caption) for t in tables] == [(2, "[표 1] 물가 전망"), (3, "< 고용 전망 >")]
	assert tables[0].rows == PRICE_ROWS
	assert tables[1].rows == [["구분", "2025"], ["실업률", "2.8"]]
	assert all(t.markdown == "" and t.source_type == "table" for t in tables)


# [확인 18] rows는 pdfplumber page.extract_tables()와 같다 (find_tables()로 위치를 받아도 행·열은 그대로)
def test_extract_tables_same_rows_as_pdfplumber(tmp_path):
	def page1(page):
		draw_table(page, 60, 100, PRICE_ROWS)
		draw_table(page, 60, 300, [["구분", "", "2025"], ["성장률", "1.0", ""]], merged={(0, 0)})

	path = make_pdf(tmp_path / "b.pdf", [page1])
	with pdfplumber.open(path) as pdf:
		expected = pdf.pages[0].extract_tables()

	assert [t.rows for t in extract_tables(path)] == expected


# [확인 19] 캡션 위치: 한 줄에 캡션이 나란히 있으면 표와 가로로 겹치는 캡션을 고르고(두 형식 모두, 앞뒤 공백 없이),
#           표 위 30pt보다 먼 캡션·표 아래 캡션은 그 표의 캡션이 아니다 (None)
def test_extract_tables_caption_position(tmp_path):
	def page1(page):
		# 좌우 배치: 왼쪽 표(x 60~220)·오른쪽 표(x 320~480), 캡션은 같은 줄
		write_text(page, 60, 92, "< 왼쪽 표 >")
		write_text(page, 320, 92, "< 오른쪽 표 >")
		draw_table(page, 60, 100, PRICE_ROWS[:2])
		draw_table(page, 320, 100, PRICE_ROWS[:2])
		# 캡션이 표 위 80pt 정도 떨어짐 (그 사이는 문단이라고 봄)
		write_text(page, 60, 320, "< 먼 캡션 >")
		draw_table(page, 60, 400, PRICE_ROWS[:2])
		# 캡션이 표 아래에만 있음
		draw_table(page, 60, 600, PRICE_ROWS[:2])
		write_text(page, 60, 660, "< 아래 캡션 >")

	def page2(page):
		# 명세서 형식 캡션 두 개가 한 줄에 (정규식이 '[표 1] 물가 '까지 잡아도 공백은 빼고 저장)
		write_text(page, 60, 92, "[표 1] 물가")
		write_text(page, 320, 92, "[표 2] 고용")
		draw_table(page, 60, 100, PRICE_ROWS[:2])
		draw_table(page, 320, 100, PRICE_ROWS[:2])

	tables = extract_tables(make_pdf(tmp_path / "c.pdf", [page1, page2]))

	assert [t.caption for t in tables] == ["< 왼쪽 표 >", "< 오른쪽 표 >", None, None, "[표 1] 물가", "[표 2] 고용"]


# [확인 20] HRI 표 위 모양 두 가지
#           - 캡션 줄과 표 사이에 '(단위: %)' 줄이 끼어 있어도 캡션 줄을 찾는다
#           - 30pt 안에 캡션이 두 개면(상자 제목 '< 참고 : … >' 아래 표 제목) 표에 더 가까운 것이 표 제목
#             (HRI '2025년 국내외 트렌드' 15쪽 모양, [확인 24]에서 실제 보고서로도 확인)
def test_extract_tables_caption_with_unit_line(tmp_path):
	def page1(page):
		write_text(page, 120, 78, "< 주요 IB의 한국 경제성장률 전망 >")
		write_text(page, 300, 94, "(단위: %)")
		draw_table(page, 60, 100, PRICE_ROWS)
		write_text(page, 60, 382, "< 참고 : 주요국 물가 비교 >")
		write_text(page, 60, 396, "< 주요국 물가 >")
		draw_table(page, 60, 400, PRICE_ROWS)

	assert [t.caption for t in extract_tables(make_pdf(tmp_path / "d.pdf", [page1]))] == [
		"< 주요 IB의 한국 경제성장률 전망 >",
		"< 주요국 물가 >",
	]


# [확인 21] 병합 칸 자리는 None, 글자 없는 칸은 ""로 그대로 남고, validate_table()이 두 칸의 좌표를 찾는다
def test_extract_tables_keeps_merged_and_empty(tmp_path):
	def page1(page):
		write_text(page, 60, 92, "< 경제 전망 >")
		# 1행 1·2열을 합친 '구 분' 칸, 2행 3열은 빈 칸
		draw_table(page, 60, 100, [["구 분", "", "2025"], ["경제", "성장률", ""], ["물가", "상승률", "2.0"]], merged={(0, 0)})

	[table] = extract_tables(make_pdf(tmp_path / "e.pdf", [page1]))

	assert table.rows == [["구 분", None, "2025"], ["경제", "성장률", ""], ["물가", "상승률", "2.0"]]
	assert validate_table(table.rows) == "⚠️ 빈 셀 1개: (2, 3) / 병합 의심 셀 1개: (1, 2)"


# ---------------------------------------------------------------------
# validate_table()
# ---------------------------------------------------------------------
# [확인 22] 빈 셀("")·병합 의심 셀(None)의 (행, 열) 좌표를 1부터 세서 경고, 없으면 '✅ 이상 없음'
@pytest.mark.parametrize("rows, expected", [
	(PRICE_ROWS, "✅ 이상 없음"),
	([["구분", "2025", "2026"], ["성장률", "", "2.0"], ["물가", "2.1", ""]], "⚠️ 빈 셀 2개: (2, 2), (3, 3)"),
	([["구분", None, "2025"], [None, "물가", "2.0"]], "⚠️ 병합 의심 셀 2개: (1, 2), (2, 1)"),
	([["구분", None], ["성장률", ""]], "⚠️ 빈 셀 1개: (2, 2) / 병합 의심 셀 1개: (1, 2)"),
])
def test_validate_table(rows, expected):
	assert validate_table(rows) == expected


# [확인 23] 표 노드가 쓰는 약속: 이상 없으면 TABLE_OK('✅'로 시작), 이상 있으면 '✅'로 시작하지 않음
def test_validate_table_matches_node_rule():
	assert validate_table(PRICE_ROWS) == TABLE_OK and TABLE_OK.startswith("✅")
	assert not validate_table([["구분", None]]).startswith("✅")


# ---------------------------------------------------------------------
# 실제 HRI 보고서 (HRI_PDF_DIR가 있을 때만)
# ---------------------------------------------------------------------
# 실행: HRI_PDF_DIR="<현대경제연구원_자료 폴더>" poetry run python -m pytest tests/test_table_loader.py -v
HRI_PDF_DIR = os.getenv("HRI_PDF_DIR", "")


def hri_pdf(name_start):
	"""HRI_PDF_DIR에서 파일 이름이 name_start로 시작하는 PDF 경로"""
	return str(next(Path(HRI_PDF_DIR).glob(f"{name_start}*.pdf")))


# [확인 24] 실제 보고서 3편
# - '3%대 성장이 남긴 과제' 9쪽 전망표: 캡션 '< … >', 13행 9열, 병합 칸 None 그대로, 병합 의심 경고
# - '2025년 국내외 트렌드' 23쪽: 한 줄에 나란히 있는 캡션 두 개가 좌우 표에 하나씩 / 15쪽: 상자 제목보다 가까운 표 제목
# - '2025년 한국 경제 전망(수정)' 3쪽: 요약 쪽의 1행 2열 상자(캡션 없음)는 caption None
# - 세 보고서 모두 rows가 pdfplumber page.extract_tables()와 같다
@pytest.mark.skipif(not HRI_PDF_DIR, reason="HRI_PDF_DIR(HRI 보고서 PDF 폴더)가 없어 실제 보고서 테스트를 건너뜀")
def test_extract_tables_real_hri_reports():
	outlook = hri_pdf("3%대 성장이 남긴 과제")
	trend = hri_pdf("2025년 국내외 트렌드")
	revised = hri_pdf("2025년 한국 경제 전망(수정)")

	[table] = [t for t in extract_tables(outlook) if t.page == 9]
	assert table.caption == "< 현대경제연구원의 2027년 한국 경제 전망표(2026년 9월) >"
	assert (len(table.rows), len(table.rows[0])) == (13, 9)
	assert table.rows[0] == ["구 분", None, "2025", "2026", None, None, "2027(E)", None, None]
	assert validate_table(table.rows).startswith("⚠️ 병합 의심 셀 17개: (1, 2), (1, 5)")

	trend_tables = extract_tables(trend)
	assert [t.caption for t in trend_tables if t.page == 23] == [
		"< 국방력 발전 5개년 계획(2021~25년) 주요 내용 >",
		"< 2024년 남북 군사력 순위 비교(145개국 기준) >",
	]
	# 15쪽: 상자 제목 '< 참고 : 주요 관세전쟁 사례 및 … >' 바로 아래 표 제목이 있음 → 표에 가까운 표 제목
	assert [t.caption for t in trend_tables if t.page == 15] == [
		"< 주요 관세전쟁 사례 >",
		"< 19세기 주요국 시기별 연평균 경제성장률 >",
	]

	[box] = [t for t in extract_tables(revised) if t.page == 3]
	assert box.caption is None and box.rows == [["GDP증가율", "2.0% ⇨ 0.7%"]]

	for path in (outlook, trend, revised):
		with pdfplumber.open(path) as pdf:
			expected = [(page.page_number, rows) for page in pdf.pages for rows in page.extract_tables()]
		assert [(t.page, t.rows) for t in extract_tables(path)] == expected
