"""지표 비교 · extract_indicators, build_compare_table, plot_indicators (장유빈)"""
import logging
import re
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from hri.dao.indicator_dao import insert_indicators, select_indicators
from hri.domain.schemas import Indicator
from hri.service.report_service import get_report_text, search_reports

from langchain_openai import ChatOpenAI

from hri.llm.llm_client import MODEL

logger = logging.getLogger(__name__)


# =====================================================================
# [장유빈] 지표 추출 · extract_indicators (WBS 3.5.11)
# 보고서 본문(섹션 원문 + 표·차트)에서 경제 지표 수치를 LLM으로 뽑아 indicators 테이블에 저장한다
# =====================================================================

# 지표 추출 답변이 길어질 수 있어 넉넉히 둔다 (gpt-5-mini는 추론 토큰도 max_tokens에 포함)
INDICATOR_MAX_TOKENS = 16000

# 지표 이름 통일표: 대표 이름 → 보고서마다 다르게 쓰는 이름들
# 보고서끼리 지표를 비교하려면 같은 지표가 같은 이름이어야 한다 (이름이 없으면 추가하면 된다)
INDICATOR_ALIASES: dict[str, list[str]] = {
	"경제성장률": ["GDP 성장률", "실질GDP 성장률", "실질 GDP 증가율", "GDP 증가율", "성장률"],
	"소비자물가 상승률": ["소비자물가", "소비자물가상승률", "CPI", "CPI 상승률", "물가 상승률", "물가상승률", "소비자물가지수 상승률"],
	"실업률": [],
	"기준금리": ["정책금리", "한국은행 기준금리"],
	"원/달러 환율": ["원달러 환율", "원-달러 환율", "원/달러", "달러 환율", "USD/KRW"],
	"경상수지": [],
	"수출 증가율": ["수출증가율", "수출 증가"],
	"수입 증가율": ["수입증가율", "수입 증가"],
}

INDICATOR_SYSTEM_PROMPT = (
	"당신은 경제 분석 보고서에서 경제 지표 수치를 뽑는 도우미입니다.\n"
	"사용자가 주는 [보고서 본문]에서 지표 수치를 모두 뽑아 목록으로 돌려줍니다.\n"
	"규칙:\n"
	"1. 본문에 실제로 적힌 수치만 뽑습니다. 추측·계산·외부 지식으로 만든 값은 넣지 않습니다.\n"
	"2. name은 보고서에 쓰인 이름 그대로 적습니다.\n"
	"3. value에는 숫자만 적습니다. 단위·기호는 빼고 음수 부호는 남깁니다.\n"
	"4. unit에는 값 옆에 붙어 있던 단위를 적습니다 (예: %, %p, 원, 억 원, 조 원).\n"
	"5. period는 연 YYYY, 분기 YYYYQn, 월 YYYYMM, 일 YYYYMMDD 중 하나로 적습니다. "
	"기준 시점을 알 수 없는 수치는 뽑지 않습니다.\n"
	"6. 실적치와 전망치는 기준 시점으로 구분해 모두 뽑습니다.\n"
	"7. source는 수치를 찾은 위치입니다. 일반 본문은 text, '[표 ...]' 블록은 table, '[차트 ...]' 블록은 chart입니다.\n"
	"8. 제목 줄에 '(추정)'이 붙은 차트 블록에서 읽은 수치는 needs_review를 true로, 그 밖의 수치는 false로 합니다.\n"
	"9. 같은 지표·같은 시점·같은 값은 한 번만 뽑습니다.\n"
	"10. 뽑을 수치가 없으면 빈 목록을 돌려줍니다."
)

# 허용하는 기준 시점 형식: 연 YYYY · 분기 YYYYQn · 월 YYYYMM · 일 YYYYMMDD
_PERIOD_PATTERN = re.compile(
	r"^(\d{4}"
	r"|\d{4}Q[1-4]"
	r"|\d{4}(0[1-9]|1[0-2])"
	r"|\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01]))$"
)


class IndicatorList(BaseModel):
	"""LLM이 한 번에 돌려주는 지표 목록. with_structured_output의 출력 형식으로 쓴다."""

	indicators: list[Indicator] = Field(description="본문에서 뽑은 지표 목록. 뽑을 수치가 없으면 빈 목록")


def _name_key(name: str) -> str:
	"""이름 비교용 열쇠: 공백을 모두 없애고 소문자로 바꾼다 ('소비자물가 상승률' == '소비자물가상승률')."""
	return re.sub(r"\s+", "", name).lower()


# 열쇠 → 대표 이름. 대표 이름 자신도 넣어 두어 공백만 다른 경우도 하나로 모은다
_ALIAS_LOOKUP: dict[str, str] = {
	_name_key(alias): canonical
	for canonical, aliases in INDICATOR_ALIASES.items()
	for alias in [canonical, *aliases]
}


def normalize_indicator_name(name: str) -> str:
	"""지표 이름을 INDICATOR_ALIASES의 대표 이름으로 통일한다. 표에 없는 이름은 앞뒤 공백만 지워 그대로 돌려준다."""
	stripped = name.strip()
	return _ALIAS_LOOKUP.get(_name_key(stripped), stripped)


def _clean_indicators(indicators: list[Indicator], report_id: int) -> list[Indicator]:
	"""LLM이 뽑은 지표를 저장하기 좋게 다듬는다.

	- report_id를 붙인다 (LLM은 채우지 않는다)
	- 이름은 대표 이름으로 통일하고, 기준 시점은 대문자로 맞춘다 (2026q2 → 2026Q2)
	- 기준 시점 형식이 틀렸거나 이름이 빈 지표는 버린다 (ECOS 비교 기간을 만들 수 없다)
	- 이름·시점·값·단위가 같은 지표는 먼저 나온 것 하나만 남긴다
	"""
	cleaned: list[Indicator] = []
	seen: set[tuple[str, str, float, str]] = set()
	for item in indicators:
		name = normalize_indicator_name(item.name)
		period = item.period.strip().upper()
		unit = item.unit.strip()
		if not name or not _PERIOD_PATTERN.match(period):
			continue
		key = (name, period, item.value, unit)
		if key in seen:
			continue
		seen.add(key)
		cleaned.append(item.model_copy(update={"report_id": report_id, "name": name, "period": period, "unit": unit}))
	return cleaned


def _request_indicators(text: str) -> IndicatorList | None:
	"""보고서 본문을 LLM에 보내 지표 목록을 받는다. 결과를 읽지 못하면 None.

	llm_client는 import할 때 .env를 읽는 모듈에 있어서, 이 함수 안에서 불러온다
	(테스트가 .env 없이도 extract_indicators의 나머지 로직을 확인할 수 있게 하려는 것).
	지표 추출은 본문의 수치를 옮겨 적는 일이라 추론 강도를 낮춘다.
	(gpt-5-mini는 추론에 max_tokens를 다 써 버리면 답이 비어 LengthFinishReasonError가 난다)
	"""

	model = ChatOpenAI(
		model=MODEL,
		max_tokens=INDICATOR_MAX_TOKENS,
		reasoning_effort="low",
	).with_structured_output(IndicatorList)
	messages = [
		{"role": "system", "content": INDICATOR_SYSTEM_PROMPT},
		{"role": "user", "content": f"[보고서 본문]\n{text}"},
	]
	return model.invoke(messages)


def extract_indicators(report_id: int) -> list[Indicator]:
	"""보고서에서 경제 지표 수치를 뽑아 돌려주고 indicators 테이블에 저장한다.

	이미 저장된 지표가 있으면 LLM을 부르지 않고 그대로 돌려준다 (같은 보고서를 다시 뽑지 않는다).
	없으면 get_report_text()의 본문을 LLM에 보내 Indicator 목록을 받고,
	_clean_indicators()로 이름·시점을 다듬은 뒤 insert_indicators()로 저장한다.
	본문이 비었거나 LLM 결과를 읽지 못하면 저장하지 않고 빈 리스트를 돌려준다.
	비교표·차트(build_compare_table, plot_indicators)가 이 결과를 사용한다.
	"""
	saved = select_indicators(report_id)
	if saved:
		return saved

	text = get_report_text(report_id)
	if not text.strip():
		return []

	result = _request_indicators(text)
	if result is None:
		return []

	indicators = _clean_indicators(result.indicators, report_id)
	insert_indicators(report_id, indicators)
	return indicators


# =====================================================================
# [장유빈] 지표 비교 · build_compare_table, plot_indicators (WBS 3.5.12)
# 선택한 보고서들의 지표를 같은 이름·시점·단위끼리 모아 표(Markdown)와 막대 차트(PNG)로 보여 준다
# =====================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # hri/service/indicator_service.py → 프로젝트 맨 위 폴더
FONT_DIR = PROJECT_ROOT / "assets" / "fonts"  # 한글 폰트 파일(.ttf·.otf)을 넣어 두는 곳 (서버에는 한글 폰트가 없다)
PLOT_DIR = PROJECT_ROOT / "data" / "plots"  # 차트 PNG 저장 폴더 (.gitignore로 커밋 제외)
# assets/fonts에 파일이 없을 때 찾아볼 컴퓨터에 설치된 한글 폰트 이름
SYSTEM_FONT_NAMES = ["NanumGothic", "Malgun Gothic", "AppleGothic", "Noto Sans CJK KR", "Noto Sans KR"]

EMPTY_CELL = "-"  # 그 보고서에 없는 지표 칸
REVIEW_MARK = "*"  # 차트에서 읽어 확인이 필요한 값(needs_review) 표시
REVIEW_NOTE = f"{REVIEW_MARK} 차트에서 읽은 추정값이라 확인이 필요합니다."
MAX_UNIT_GROUPS = 3  # 차트 하나에 그리는 단위 묶음 수 (단위가 같은 지표끼리 한 칸)
MAX_BARS_PER_GROUP = 8  # 한 칸에 그리는 지표·시점 수 (너무 많으면 글자가 겹친다)
LEGEND_TITLE_LENGTH = 20  # 범례에 쓰는 보고서 제목의 최대 글자 수

# (지표 이름, 시점, 단위) → {report_id: Indicator}
_Rows = dict[tuple[str, str, str], dict[int, Indicator]]


def _format_value(value: float) -> str:
	"""값을 읽기 좋게 바꾼다: 1390.0 → '1,390', 2.50 → '2.5', -0.3 → '-0.3'."""
	text = f"{value:,.2f}".rstrip("0").rstrip(".")
	return "0" if text in ("-0", "") else text


def _report_titles(report_ids: list[int]) -> dict[int, str]:
	"""report_id → 표 머리글에 쓸 보고서 제목. 제목이 같은 보고서가 있으면 '제목 (#번호)'로 구분한다."""
	found = {r.report_id: r.title for r in search_reports("")}
	titles = {rid: found.get(rid) or f"보고서 #{rid}" for rid in report_ids}
	counts: dict[str, int] = {}
	for title in titles.values():
		counts[title] = counts.get(title, 0) + 1
	return {rid: f"{t} (#{rid})" if counts[t] > 1 else t for rid, t in titles.items()}


def _collect_rows(report_ids: list[int]) -> _Rows:
	"""보고서마다 extract_indicators()로 지표를 가져와 (이름, 시점, 단위)별로 모은다.

	한 보고서에 같은 (이름, 시점, 단위)가 여러 개면 먼저 나온 값 하나만 쓴다 (pivot_table의 aggfunc='first'와 같다).
	"""
	rows: _Rows = {}
	for report_id in report_ids:
		for item in extract_indicators(report_id):
			rows.setdefault((item.name, item.period, item.unit), {}).setdefault(report_id, item)
	return rows


def _sorted_keys(rows: _Rows) -> list[tuple[str, str, str]]:
	"""여러 보고서에 함께 나온 지표가 위로 오게 정렬한다. 같으면 이름·시점·단위 순."""
	return sorted(rows, key=lambda key: (-len(rows[key]), key))


def _escape_cell(text: str) -> str:
	"""Markdown 표 칸에 넣을 글자에서 표를 깨는 '|'와 줄바꿈을 바꾼다."""
	return text.replace("|", "\\|").replace("\n", " ")


def _rows_to_markdown(header: list[str], body: list[list[str]]) -> str:
	"""머리글과 행 목록을 Markdown 표 문자열로 만든다. (table_to_markdown(엄정현)이 들어오면 그것으로 바꾼다)"""
	lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
	lines.extend("| " + " | ".join(row) + " |" for row in body)
	return "\n".join(lines)


def build_compare_table(report_ids: list[int]) -> str:
	"""선택한 보고서들의 지표를 한 표(Markdown)로 비교한다.

	행은 (지표 이름, 시점, 단위), 열은 보고서 제목이다. 그 보고서에 없는 칸은 '-'로 채우고,
	차트에서 읽어 확인이 필요한 값(needs_review)에는 '*'를 붙인 뒤 표 아래에 설명을 적는다.
	여러 보고서에 함께 나온 지표가 위로 온다. 지표가 하나도 없으면 빈 문자열을 돌려준다.
	"""
	report_ids = list(dict.fromkeys(report_ids))  # 중복 번호 제거 (순서 유지)
	rows = _collect_rows(report_ids)
	if not rows:
		return ""

	titles = _report_titles(report_ids)
	header = ["지표", "시점", "단위", *(_escape_cell(titles[rid]) for rid in report_ids)]
	body = []
	has_review = False
	for key in _sorted_keys(rows):
		cells = []
		for report_id in report_ids:
			item = rows[key].get(report_id)
			if item is None:
				cells.append(EMPTY_CELL)
				continue
			mark = REVIEW_MARK if item.needs_review else ""
			has_review = has_review or item.needs_review
			cells.append(_format_value(item.value) + mark)
		body.append([_escape_cell(key[0]), key[1], _escape_cell(key[2]) or EMPTY_CELL, *cells])

	table = _rows_to_markdown(header, body)
	return f"{table}\n\n{REVIEW_NOTE}" if has_review else table


def _use_korean_font() -> str | None:
	"""차트에 쓸 한글 폰트 이름을 정해 돌려준다. 없으면 None.

	assets/fonts의 .ttf·.otf 파일을 먼저 등록해 쓰고, 파일이 없으면 컴퓨터에 설치된 한글 폰트를 찾는다.
	"""
	from matplotlib import font_manager

	for path in sorted([*FONT_DIR.glob("*.ttf"), *FONT_DIR.glob("*.otf")]):
		try:
			font_manager.fontManager.addfont(str(path))
			return font_manager.FontProperties(fname=str(path)).get_name()
		except (OSError, RuntimeError):
			logger.warning("폰트 파일을 읽지 못했습니다: %s", path)
	installed = {f.name for f in font_manager.fontManager.ttflist}
	for name in SYSTEM_FONT_NAMES:
		if name in installed:
			return name
	logger.warning("한글 폰트를 찾지 못했습니다. assets/fonts에 폰트 파일(예: NanumGothic.ttf)을 넣어 주세요.")
	return None


def _shorten(text: str, length: int = LEGEND_TITLE_LENGTH) -> str:
	"""긴 제목은 length글자에서 자르고 '…'를 붙인다."""
	return text if len(text) <= length else text[: length - 1] + "…"


def plot_indicators(report_ids: list[int]) -> str | None:
	"""선택한 보고서들의 지표를 막대 차트(PNG)로 그리고 파일 경로를 돌려준다.

	단위가 같은 지표끼리만 한 칸에 그린다 (%와 원을 한 축에 섞지 않는다). 칸마다 가로축은 '지표·시점',
	막대 색은 보고서다. 2개 이상의 보고서에 함께 나온 지표만 그리고, 차트에서 읽은 추정값(needs_review)은
	빗금 막대에 '*'를 붙인다. 파일 이름에 uuid를 붙여 동시에 써도 겹치지 않는다.
	그릴 지표가 없으면(공통 지표 없음) None을 돌려준다.
	"""
	import matplotlib

	matplotlib.use("Agg")  # 화면 없는 서버에서도 그릴 수 있게 한다
	from matplotlib.figure import Figure

	report_ids = list(dict.fromkeys(report_ids))
	rows = _collect_rows(report_ids)
	shared = [key for key in _sorted_keys(rows) if len(rows[key]) >= 2]
	if not shared:
		return None

	# 단위별로 묶고, 지표가 많은 단위부터 MAX_UNIT_GROUPS개만 그린다
	by_unit: dict[str, list[tuple[str, str, str]]] = {}
	for key in shared:
		by_unit.setdefault(key[2], []).append(key)
	units = sorted(by_unit, key=lambda unit: -len(by_unit[unit]))[:MAX_UNIT_GROUPS]

	titles = _report_titles(report_ids)
	font = _use_korean_font()
	rc = {"axes.unicode_minus": False}
	if font:
		rc["font.family"] = font

	with matplotlib.rc_context(rc):
		longest = max(min(len(by_unit[u]), MAX_BARS_PER_GROUP) for u in units)
		fig = Figure(figsize=(min(14, max(7, 1.4 * longest + 3)), 3.8 * len(units)))
		axes = fig.subplots(len(units), 1, squeeze=False)[:, 0]
		colors = [f"C{i}" for i in range(len(report_ids))]
		has_review = False
		width = 0.8 / len(report_ids)

		for ax, unit in zip(axes, units):
			keys = by_unit[unit][:MAX_BARS_PER_GROUP]
			labels = [f"{name}\n{period}" for name, period, _ in keys]
			for i, report_id in enumerate(report_ids):
				xs, heights, reviews = [], [], []
				for j, key in enumerate(keys):
					item = rows[key].get(report_id)
					if item is not None:
						xs.append(j + (i - (len(report_ids) - 1) / 2) * width)
						heights.append(item.value)
						reviews.append(item.needs_review)
				bars = ax.bar(xs, heights, width, color=colors[i], label=_shorten(titles[report_id]))
				for bar, review in zip(bars, reviews):
					if review:
						has_review = True
						bar.set_hatch("//")
						bar.set_alpha(0.6)
				ax.bar_label(bars, labels=[_format_value(h) + (REVIEW_MARK if r else "") for h, r in zip(heights, reviews)], fontsize=8, padding=2)
			ax.set_xticks(range(len(keys)), labels, fontsize=9)
			ax.set_ylabel(unit or "단위 없음")
			ax.axhline(0, color="gray", linewidth=0.6)
			ax.margins(y=0.15)

		axes[0].legend(fontsize=8, loc="best")
		fig.suptitle("보고서별 지표 비교", fontsize=13)
		if has_review:
			fig.text(0.99, 0.005, REVIEW_NOTE, ha="right", va="bottom", fontsize=8, color="gray")
		fig.tight_layout(rect=(0, 0.02, 1, 0.97))

		PLOT_DIR.mkdir(parents=True, exist_ok=True)
		path = PLOT_DIR / f"compare_{uuid.uuid4().hex}.png"
		fig.savefig(path, dpi=150)
	return str(path)