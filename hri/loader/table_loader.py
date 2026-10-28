"""표 추출·요약 · extract_tables, validate_table, table_to_markdown, split_big_table, summarize_tables (엄정현)"""

# 엄정현 table_to_markdown()·split_big_table() 추가 (WBS 3.2.7).
# - split_big_table()의 header_rows 인자(머리글 2줄 이상인 표)는 명세서에 없는 추가 기능이다 (함수 설명 참고).
# - extract_tables_node()(graph/ingest_graph)가 split_big_table()로 큰 표를 나누고, 조각마다 table_to_markdown()으로 마크다운 표를 만든다.
# - table_to_markdown()은 chart_to_markdown()(차트 → 표), build_compare_table()(지표 비교표), get_dashboard_data()(대시보드 표)에서도 쓴다.
# 엄정현 extract_tables()·validate_table() 추가 (WBS 3.2.10).
# - extract_tables_node()가 extract_tables() → validate_table() → split_big_table() → table_to_markdown() 순서로 부른다.
# - 캡션 정규식은 명세서의 '[표 n]'과 HRI 보고서의 '< 제목 >'(번호 없음) 두 형식을 모두 잡는다.

import re

import pdfplumber

from hri.domain.schemas import Table

# 셀 안의 줄바꿈·연속 공백. pdfplumber는 칸 안에서 줄이 바뀐 곳에 '\n'을 넣는다
# 예) HRI 보고서 표 칸 '‣ … 경제\n및 사회 환경의 급변은 …' → 마크다운 표는 한 줄이어야 하므로 공백 1칸으로 바꾼다
CELL_SPACES = re.compile(r"\s+")

# 큰 표를 나누는 기준: 머리글을 뺀 본문 행 수 (명세서 split_big_table 행: max_rows 기본값 10)
MAX_TABLE_ROWS = 10


def _clean_cell(cell: str | None) -> str:
	"""셀 1칸을 마크다운 표에 넣을 글로 바꾼다.

	- None → 빈칸 "" (pdfplumber는 병합된 칸 자리를 None, 글자가 없는 칸을 ""로 돌려준다)
	- 줄바꿈·연속 공백 → 공백 1칸, 앞뒤 공백 제거
	- '|'는 마크다운 표의 칸 나눔 기호라, 글자로 남기도록 '\\|'로 바꾼다 (칸 수가 늘어나지 않게)
	- str()로 감싸는 이유: 비교표·대시보드에서 숫자를 그대로 넘겨도 표가 만들어지게
	"""
	if cell is None:
		return ""
	text = CELL_SPACES.sub(" ", str(cell)).strip()
	return text.replace("|", "\\|")


def _markdown_row(cells: list[str]) -> str:
	"""칸 목록을 마크다운 표 한 줄로 만든다. 예) ['연도', '물가'] → '| 연도 | 물가 |'"""
	return "| " + " | ".join(cells) + " |"


def table_to_markdown(rows: list[list[str | None]]) -> str:
	"""rows(첫 행 = 머리글)를 LLM이 읽기 쉬운 마크다운 표 글 1개로 만든다.

	순서 (명세서 table_to_markdown 행): 머리글 줄 → 구분선 줄(|---|---|) → 본문 줄
		| 연도 | 물가상승률 |
		|---|---|
		| 2025 | 2.1 |
	- 셀 정리는 _clean_cell() (None은 빈칸, 줄바꿈은 공백, '|'는 '\\|')
	- rows가 비어 있으면 "" (만들 표가 없음)
	"""
	if not rows:
		return ""
	header, *body = [[_clean_cell(cell) for cell in row] for row in rows]
	lines = [_markdown_row(header), "|" + "|".join(["---"] * len(header)) + "|"]
	lines += [_markdown_row(row) for row in body]
	return "\n".join(lines)


def split_big_table(
	rows: list[list[str | None]],
	max_rows: int = MAX_TABLE_ROWS,
	header_rows: int = 1,
) -> list[list[list[str | None]]]:
	"""본문이 max_rows행을 넘는 표를 max_rows행씩 나누고, 모든 조각 맨 앞에 머리글을 붙인다.

	명세서 split_big_table 행 그대로 (header_rows=1, 기본값)
	- 머리글 = 첫 줄 rows[0]. 표가 잘려도 조각마다 머리글이 있어서, 조각 하나만 검색·답변에 쓰여도 각 칸이 무엇인지 알 수 있다
	  예) 본문 23행 → [머리글 + 1~10행], [머리글 + 11~20행], [머리글 + 21~23행]
	- 본문이 max_rows행 이하면 나누지 않고 [rows] 그대로
	- rows가 비어 있으면 [] (만들 조각이 없음)
	- 조각 캡션의 '(1/n)'은 표 노드(extract_tables_node)가 붙인다
	- max_rows가 1보다 작으면 ValueError (0이면 나눌 수 없고, 음수면 조각이 0개가 되어 표가 사라짐)

	[추가 기능 · 명세서 밖] header_rows: 머리글 줄 수 (기본 1 = 명세서와 같음)
	- 왜: HRI 전망 표는 머리글이 2줄인 경우가 있다 (1줄 '2025 | 2026 | 2027(E)', 2줄 '상반 | 하반 | 연간').
	  첫 줄만 붙이면 둘째 조각부터 '상반·하반·연간' 줄이 빠져 숫자가 어느 칸인지 알 수 없다
	  (HRI 5편 점검: 본문 10행 초과 표 9개 중 5개가 이 모양)
	- 어떻게: 앞 header_rows줄을 머리글로 보고 조각마다 모두 붙인다. 본문 행 수도 그 줄을 뺀 나머지로 센다
	  예) header_rows=2, 본문 12행 → [머리글 2줄 + 1~10행], [머리글 2줄 + 11~12행]
	- 몇 줄인지는 이 함수가 판단하지 않는다. 부르는 쪽이 정해서 넘긴다
	  (지금 표 노드는 넘기지 않아 1줄로 동작. 표마다 줄 수를 정하는 규칙은 3.2.10 extract_tables에서 정할 일)
	- header_rows가 1보다 작으면 ValueError (머리글 없이 나누면 조각의 칸 이름이 사라짐)
	"""
	if max_rows < 1:
		raise ValueError(f"max_rows는 1 이상이어야 합니다: {max_rows}")
	if header_rows < 1:
		raise ValueError(f"header_rows는 1 이상이어야 합니다: {header_rows}")
	if not rows:
		return []
	header, body = rows[:header_rows], rows[header_rows:]
	if len(body) <= max_rows:
		return [rows]
	return [header + body[start:start + max_rows] for start in range(0, len(body), max_rows)]


# ── extract_tables·validate_table (WBS 3.2.10) ───────────────────────────────
# 표 캡션: 두 형식 중 하나
#   ① 명세서 형식 '[표 1] 제목'  : '[표 n]'부터 그 줄 끝까지 (같은 줄에 다음 '[표'가 오면 그 앞까지)
#   ② HRI 형식   '< 제목 >'     : 번호가 없고, 꺾쇠 안에 글자가 있어야 함 ('< >'처럼 빈 꺾쇠는 제외)
#      HRI 37편은 표 제목이 '< … >' 한 줄이다 (HRI 양식 패턴분석 10/21: '표 1' 같은 번호 없음)
# 한 줄 안에서만 찾는다(줄바꿈 제외). 두 줄로 나뉜 캡션은 둘째 줄에 옆 그림의 캡션이 섞여 있어 이어 붙이지 않는다
# 예) '물가 안정' 보고서 9쪽 둘째 줄 '물가상승률 및 기여도 한국가스공사 누적 미수금' (왼쪽 표 + 오른쪽 그림 캡션)
# → HRI 37편 표 294개 중 이런 두 줄 캡션 표 7개('물가 안정' 7~12쪽)는 caption이 None (알려진 한계)
CAPTION = re.compile(r"\[\s*표\s*\d+\s*\][^\n\[]*|<\s*[^<>\s][^<>\n]*>")

# 캡션을 찾는 범위: 표 위쪽 30pt(약 2줄) 안
# HRI 37편 점검: 캡션 아래 끝 ~ 표 위 끝 거리는 1~28pt(캡션과 표 사이에 '(단위: %)' 줄이 끼는 경우 포함),
# 그다음이 70pt 이상(다른 그림·문단의 캡션)이라 30pt로 나눴다
CAPTION_MAX_GAP = 30

# validate_table()이 이상이 없을 때 돌려주는 글 (명세서 validate_table 행: "'✅ 이상 없음' 또는 경고를 반환")
TABLE_OK = "✅ 이상 없음"


def _find_caption(captions: list[dict], bbox: tuple) -> str | None:
	"""같은 쪽의 캡션 후보 중 표 바로 위에 있는 것을 고른다. 없으면 None.

	captions: page.search(CAPTION)의 결과 (글자 text와 위치 x0·x1·top·bottom)
	bbox    : 표의 위치 (x0, top, x1, bottom). pdfplumber 좌표는 쪽 위가 0이고 아래로 갈수록 커진다
	고르는 규칙
	- 표 위 끝(top)보다 위에 있고, 거리가 CAPTION_MAX_GAP(30pt) 이하
	- 가로 범위가 표와 겹침: HRI는 한 줄에 '< 왼쪽 표 제목 > < 오른쪽 그림 제목 >'처럼 두 캡션이 나란히 있어서,
	  표 위에 있는 쪽 캡션만 고른다
	- 그중 표에 가장 가까운(아래 끝이 가장 큰) 것
	"""
	x0, top, x1, _ = bbox
	above = [
		c for c in captions
		if c["bottom"] <= top and top - c["bottom"] <= CAPTION_MAX_GAP and c["x0"] < x1 and c["x1"] > x0
	]
	if not above:
		return None
	return max(above, key=lambda c: c["bottom"])["text"].strip()


def extract_tables(file_path: str) -> list[Table]:
	"""PDF의 표를 행·열 구조 그대로 뽑아 쪽 번호·캡션과 함께 list[Table]로 돌려준다.

	순서 (명세서 extract_tables 행)
	1. pdfplumber.open(file_path)로 열고 쪽마다 표를 찾는다
	   - page.extract_tables()는 안에서 find_tables()로 찾은 표마다 .extract()를 부른 결과다.
	     캡션을 찾으려면 표의 위치(bbox)가 필요해서 find_tables()로 표를 받고 .extract()로 rows를 만든다 (rows는 같음)
	2. rows: 머리글 행 + 본문 행. 병합된 칸 자리는 None, 글자가 없는 칸은 "" (pdfplumber가 돌려준 그대로)
	   → validate_table()이 None(병합 의심)과 ""(빈 셀)를 구분해 좌표를 찾는다
	3. page: page.page_number (1부터)
	4. caption: 표 위 30pt 안의 '[표 n] …' 또는 '< 제목 >' (_find_caption). 없으면 None
	markdown은 비워 둔다 (표 노드가 split_big_table() → table_to_markdown()으로 채움).
	validate_pdf()를 통과한 파일만 들어온다고 보고, 열리지 않는 파일은 pdfplumber 예외를 그대로 낸다 (load_pdf()와 같음).

	예) extract_tables("data/raw/report.pdf")
	    → [Table(page=12, caption='< IMF의 주요국 경제성장률 전망(%) >', rows=[['구 분', None, …], …]), …]
	"""
	tables = []

	# with: 다 읽으면 파일을 꼭 닫는다 (load_pdf()·validate_pdf()와 같은 이유: Windows 파일 잠김)
	with pdfplumber.open(file_path) as pdf:
		for page in pdf.pages:
			found = page.find_tables()
			if not found:
				continue
			# 캡션 후보는 표가 있는 쪽에서만 찾는다 (return_chars=False: 글자 하나하나의 정보는 필요 없음)
			captions = page.search(CAPTION, return_chars=False)
			for table in found:
				tables.append(Table(
					page=page.page_number,
					caption=_find_caption(captions, table.bbox),
					rows=table.extract(),
				))

	return tables


def _cells_to_text(cells: list[tuple[int, int]]) -> str:
	"""좌표 목록을 '(1, 2), (3, 4)' 글로 만든다."""
	return ", ".join(f"({row}, {col})" for row, col in cells)


def validate_table(rows: list[list[str | None]]) -> str:
	"""표 rows에서 빈 셀·병합 의심 셀의 (행, 열) 좌표를 찾아 '✅ 이상 없음' 또는 경고 글을 돌려준다.

	- 빈 셀      : 칸은 있지만 글자가 없음 (""). pdfplumber는 글자가 없는 칸을 ""로 돌려준다
	  (공백만 있는 칸은 따로 보지 않음: HRI·타사 보고서 45편의 표 칸 13,035개 중 0개)
	- 병합 의심 셀: None. pdfplumber는 여러 칸이 하나로 합쳐진 자리(병합 칸)를 None으로 돌려준다
	- 좌표는 사람이 읽기 쉽게 1부터 센다 (쪽 번호와 같음). (1, 2) = 1행(머리글) 2열
	- 이상이 있으면 '⚠️'로 시작하는 경고. 표 노드는 '✅'로 시작하지 않으면 warnings에 '쪽·캡션·경고'를 넣고 표는 그대로 저장한다

	예) [['구분', None, '2025'], ['성장률', '', '2.0']]
	    → '⚠️ 빈 셀 1개: (2, 2) / 병합 의심 셀 1개: (1, 2)'
	"""
	empty = []
	merged = []
	for row_no, row in enumerate(rows, start=1):
		for col_no, cell in enumerate(row, start=1):
			if cell is None:
				merged.append((row_no, col_no))
			elif cell == "":
				empty.append((row_no, col_no))

	if not empty and not merged:
		return TABLE_OK

	parts = []
	if empty:
		parts.append(f"빈 셀 {len(empty)}개: {_cells_to_text(empty)}")
	if merged:
		parts.append(f"병합 의심 셀 {len(merged)}개: {_cells_to_text(merged)}")
	return "⚠️ " + " / ".join(parts)
