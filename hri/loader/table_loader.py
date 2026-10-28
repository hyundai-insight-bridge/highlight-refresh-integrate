"""표 추출·요약 · extract_tables, validate_table, table_to_markdown, split_big_table, summarize_tables (엄정현)"""

# 엄정현 table_to_markdown()·split_big_table() 추가 (WBS 3.2.7).
# - split_big_table()의 header_rows 인자(머리글 2줄 이상인 표)는 명세서에 없는 추가 기능이다 (함수 설명 참고).
# - extract_tables_node()(graph/ingest_graph)가 split_big_table()로 큰 표를 나누고, 조각마다 table_to_markdown()으로 마크다운 표를 만든다.
# - table_to_markdown()은 chart_to_markdown()(차트 → 표), build_compare_table()(지표 비교표), get_dashboard_data()(대시보드 표)에서도 쓴다.

import re

# 셀 안의 줄바꿈·연속 공백. pdfplumber는 칸 안에서 줄이 바뀐 곳에 '\n'을 넣는다
# 예) HRI 보고서 표 칸 '‣ … 경제\n및 사회 환경의 급변은 …' → 마크다운 표는 한 줄이어야 하므로 공백 1칸으로 바꾼다
CELL_SPACES = re.compile(r"\s+")

# 큰 표를 나누는 기준: 머리글을 뺀 본문 행 수 (명세서 split_big_table 행: max_rows 기본값 10)
MAX_TABLE_ROWS = 10


def _clean_cell(cell: str | None) -> str:
	"""셀 1칸을 마크다운 표에 넣을 글로 바꾼다.

	- None → 빈칸 "" (pdfplumber는 병합된 칸·빈 칸을 None으로 돌려준다)
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
	rows: list[list[str]] | None,
	max_rows: int = MAX_TABLE_ROWS,
	header_rows: int = 1,
) -> list[list[list[str]]]:
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
