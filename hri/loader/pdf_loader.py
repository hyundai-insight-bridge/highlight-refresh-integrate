"""텍스트·메타데이터 추출 · load_pdf, clean_text, find_body_start, extract_report_meta (엄정현)"""

# 엄정현 load_pdf()·clean_text()·find_body_start() 추가.
# 세 함수는 load_text_node()(graph/ingest_graph)가 load_pdf() → clean_text() → find_body_start() 순서로 부른다.

import math
import re
from collections import Counter

import pymupdf

from hri.domain.schemas import Page

# ---------------------------------------------------------------------
# clean_text()에서 쓰는 값
# ---------------------------------------------------------------------
# 머리말·꼬리말을 찾을 범위: 쪽마다 위에서 2줄, 아래에서 2줄
# (HRI 본문 쪽은 1줄 보고서 제목, 2줄 쪽 번호 / 요약 쪽은 1줄 EXECUTIVE SUMMARY, 2줄 i·ii)
EDGE_LINES = 2

# 위·아래 범위에서 같은 줄이 전체 쪽의 절반 이상(그리고 2쪽 이상)에 나오면 머리말·꼬리말로 보고 지운다
# 2쪽만 보면 '자료 : 한국은행.' 같은 표 출처 줄도 지워져서 비율로 정함 (HRI 37편 점검: 보고서 제목 줄 65~100%, 출처 줄 최대 32%)
MIN_REPEAT_RATIO = 0.5
MIN_REPEAT = 2

# 쪽 번호 줄: '1', '12', '- 3 -', 'i', 'ii', 'ⅰ' 처럼 숫자·로마 숫자만 있는 줄
# 쪽마다 숫자가 달라 그대로는 Counter로 셀 수 없으므로 '<쪽번호:위>'·'<쪽번호:아래>'로 바꿔서 센다
# (위·아래를 나눈 이유: HRI는 쪽 번호가 위에 있고, 아래 2줄의 숫자는 그래프 눈금·표 칸인 경우가 많음)
PAGE_NO_LINE = re.compile(r"-?\s*(\d{1,3}|[ivx]{1,5}|[ⅰ-ⅻ]{1,3}|[Ⅰ-Ⅻ]{1,3})\s*-?", re.IGNORECASE)

# 깨진 글자: 한글 문서(HWP)의 수식이 PDF에서 개인 사용 영역(U+E000~U+F8FF) 글자로 나온다
# 예) '잠재GDP' → '잠재\ue006\ue003\ue00f'. pymupdf·pypdf 모두 같은 글자가 나와서 읽을 수 없으므로 지운다
BROKEN_CHARS = re.compile(r"[\ue000-\uf8ff]")

# ---------------------------------------------------------------------
# find_body_start()에서 쓰는 값
# ---------------------------------------------------------------------
# 목차 쪽 제목: '목 차', '목차', 'CONTENTS' (쪽 위 3줄 안에서 찾음)
TOC_TITLE = re.compile(r"목\s*차|contents", re.IGNORECASE)
TOC_TITLE_LINES = 3

# 목차 줄: '1. 개요······ 1' 처럼 점선 뒤에 쪽 번호가 붙은 줄은 본문 시작으로 보지 않는다
TOC_LEADER = re.compile(r"[·.…]{3,}\s*\S{1,4}$")

# 본문 시작 패턴 ① 요약 쪽 제목: 줄 전체가 'Executive Summary' 또는 '요약' (HRI는 목차 다음이 요약 쪽)
SUMMARY_TITLE = re.compile(r"executive\s*summary|요\s*약", re.IGNORECASE)

# 본문 시작 패턴 ② 1장 제목: 줄 앞부분이 '1. 개요', 'Ⅰ. 최근 동향' ('1.1%'처럼 점 뒤가 숫자면 제외)
CHAPTER_ONE = re.compile(r"(1|Ⅰ|I)\s*[.．]\s*[^\d\s.]")


# ---------------------------------------------------------------------
# 1. 페이지별 추출
# ---------------------------------------------------------------------
def load_pdf(file_path: str) -> list[Page]:
	"""PDF를 열어 쪽마다 글자를 뽑아 list[Page]로 돌려준다.

	쪽 번호는 1부터 센다 (pymupdf의 쪽 인덱스는 0부터라서 +1).
	글자가 하나도 없는 쪽(스캔본·빈 쪽)은 is_scanned=True로 표시만 하고 막지 않는다.
	경고 문구는 load_text 노드가 warnings에 기록한다.
	validate_pdf()를 통과한 파일만 들어온다고 보고, 열리지 않는 파일은 pymupdf 예외를 그대로 낸다.

	예) load_pdf("data/raw/report.pdf") → [Page(page=1, text='물가 안정...', is_scanned=False), ...]
	"""
	pages = []

	# with: 다 읽으면 파일을 꼭 닫는다 (validate_pdf()와 같은 이유: Windows 파일 잠김)
	with pymupdf.open(file_path) as doc:
		for index, pdf_page in enumerate(doc):
			text = pdf_page.get_text()
			# strip() 뒤에 빈 글자면 글자가 없는 쪽 (공백·줄바꿈만 있는 쪽도 포함)
			is_scanned = text.strip() == ""
			pages.append(Page(page=index + 1, text=text, is_scanned=is_scanned))

	return pages


# ---------------------------------------------------------------------
# 2. 텍스트 정제
# ---------------------------------------------------------------------
def _line_key(line: str, where: str) -> str:
	"""Counter로 셀 때 쓰는 줄 이름. 쪽 번호 줄은 위치(where: '위'·'아래')별로 하나로 센다.

	예) _line_key('12', '위') → '<쪽번호:위>' / _line_key('물가 안정', '위') → '물가 안정'
	"""
	if PAGE_NO_LINE.fullmatch(line):
		return f"<쪽번호:{where}>"
	return line


def _split_lines(text: str) -> list[str]:
	"""글을 줄 단위로 나누고, 줄마다 연속 공백을 한 칸으로 줄인 뒤 빈 줄은 버린다."""
	lines = []
	for line in text.splitlines():
		# \s+: 공백·탭·전각 공백·줄바꿈 없는 공백(\xa0)이 여러 개 이어진 것
		line = re.sub(r"\s+", " ", line).strip()
		if line:
			lines.append(line)
	return lines


def clean_text(pages: list[Page]) -> list[Page]:
	"""여러 쪽에 반복되는 머리말·꼬리말 줄을 지우고 공백을 정리한 list[Page]를 돌려준다.

	1) 쪽마다 위 EDGE_LINES줄·아래 EDGE_LINES줄을 모아 Counter로 몇 쪽에 나오는지 센다
	   (한 쪽에서 같은 줄이 두 번 나와도 1번으로 센다)
	2) 전체 쪽의 MIN_REPEAT_RATIO(절반) 이상, MIN_REPEAT(2)쪽 이상 나온 줄을 머리말·꼬리말로 보고
	   그 쪽의 위·아래 범위에서만 지운다
	   (본문 가운데의 '자료 : 국가데이터처' 같은 줄은 여러 쪽에 있어도 지우지 않는다)
	3) re.sub()로 연속 공백을 한 칸으로 줄이고, 빈 줄과 깨진 글자(수식)를 지운다
	쪽 번호(page)와 is_scanned는 그대로 두고, 들어온 pages는 바꾸지 않는다 (model_copy로 새로 만듦).

	예) 본문 쪽 '물가 안정, 이제는 장기전으로\\n1\\n1. 개요\\n...' → '1. 개요\\n...'
	"""
	# 1) 쪽마다 줄을 나눠 두고, 위·아래 범위의 줄을 센다
	page_lines = [_split_lines(page.text) for page in pages]

	counter = Counter()
	for lines in page_lines:
		top_keys = set(_line_key(line, "위") for line in lines[:EDGE_LINES])
		bottom_keys = set(_line_key(line, "아래") for line in lines[-EDGE_LINES:])
		# set 합치기(|): 한 쪽에서 같은 줄이 위·아래에 모두 있어도 1번으로 센다
		counter.update(top_keys | bottom_keys)

	# 예) 15쪽 보고서 → 8쪽 이상 / 3쪽 → 2쪽 이상 / 1쪽 → 지우지 않음
	min_count = max(MIN_REPEAT, math.ceil(len(pages) * MIN_REPEAT_RATIO))
	repeated = {key for key, count in counter.items() if count >= min_count}

	# 2) 위·아래 범위에 있는 반복 줄만 지운다
	cleaned = []
	for page, lines in zip(pages, page_lines):
		kept = []
		for i, line in enumerate(lines):
			is_header = i < EDGE_LINES and _line_key(line, "위") in repeated
			is_footer = i >= len(lines) - EDGE_LINES and _line_key(line, "아래") in repeated
			if is_header or is_footer:
				continue
			kept.append(line)

		# 3) 깨진 글자를 지우고, 그 때문에 빈 줄이 되면 버린다
		text = "\n".join(kept)
		text = BROKEN_CHARS.sub("", text)
		text = re.sub(r"[ \t]+\n", "\n", text)  # 깨진 글자를 지운 자리에 남은 줄 끝 공백
		text = re.sub(r"\n{2,}", "\n", text).strip()

		cleaned.append(page.model_copy(update={"text": text}))

	return cleaned


# ---------------------------------------------------------------------
# 3. 본문 시작 찾기
# ---------------------------------------------------------------------
def _find_toc_index(pages: list[Page]) -> int | None:
	"""목차 쪽의 리스트 위치(0부터)를 돌려준다. 쪽 위 TOC_TITLE_LINES줄 안에 '목차'가 없으면 None."""
	for index, page in enumerate(pages):
		top_lines = page.text.splitlines()[:TOC_TITLE_LINES]
		for line in top_lines:
			if TOC_TITLE.fullmatch(line.strip()):
				return index
	return None


def _is_body_start(line: str) -> bool:
	"""이 줄이 본문 시작 패턴과 맞으면 True. 목차 줄('1. 개요····· 1')은 False."""
	line = line.strip()
	if TOC_LEADER.search(line):
		return False
	# fullmatch: 줄 전체가 같아야 함 / match: 줄 앞부분만 맞으면 됨
	if SUMMARY_TITLE.fullmatch(line) or CHAPTER_ONE.match(line):
		return True
	return False


def find_body_start(pages: list[Page]) -> list[Page]:
	"""표지·목차를 잘라 내고 본문 시작 쪽부터의 list[Page]를 돌려준다. clean_text() 다음에 실행한다.

	1) '목차' 쪽을 먼저 찾는다. HRI 목차 쪽에도 '1. 개요······ 1'이 있어서
	   처음부터 패턴을 찾으면 목차 쪽을 본문으로 잘못 고르기 때문이다
	2) 목차 다음 쪽부터(목차가 없으면 첫 쪽부터) 줄마다 SUMMARY_TITLE·CHAPTER_ONE을 확인한다
	   HRI는 목차 다음이 'Executive Summary' 쪽이라 요약 쪽부터 남는다 (요약도 본문 내용)
	3) 찾은 쪽은 그 줄 앞부분을 잘라 내고, 그 뒤 쪽은 그대로 붙인다
	못 찾으면 pages를 그대로 돌려준다 (안전장치: 본문을 통째로 잃지 않게).

	예) [표지(1쪽), 목차(2쪽), 요약(3쪽), ...] → [요약(3쪽), ...]
	"""
	toc_index = _find_toc_index(pages)
	start = 0 if toc_index is None else toc_index + 1

	for index in range(start, len(pages)):
		lines = pages[index].text.splitlines()
		for line_no, line in enumerate(lines):
			if _is_body_start(line):
				# 패턴이 나온 줄부터 남긴다 (같은 쪽에 목차 끝부분이 함께 있는 보고서 대비)
				body_text = "\n".join(lines[line_no:])
				first_page = pages[index].model_copy(update={"text": body_text})
				return [first_page] + pages[index + 1:]

	return pages