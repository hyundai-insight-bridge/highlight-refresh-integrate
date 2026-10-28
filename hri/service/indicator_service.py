"""지표 비교 · extract_indicators, build_compare_table, plot_indicators (장유빈)"""
import re

from pydantic import BaseModel, Field

from hri.dao.indicator_dao import insert_indicators, select_indicators
from hri.domain.schemas import Indicator
from hri.service.report_service import get_report_text


# =====================================================================
# [장유빈] 지표 추출 · extract_indicators (WBS 3.5.11)
# 보고서 본문(섹션 원문 + 표·차트)에서 경제 지표 수치를 LLM으로 뽑아 indicators 테이블에 저장한다
# =====================================================================

# 지표 추출 답변이 길어질 수 있어 넉넉히 둔다 (gpt-5-mini는 추론 토큰도 max_tokens에 포함)
INDICATOR_MAX_TOKENS = 4000

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

	get_chat_model은 import할 때 .env를 읽는 모듈에 있어서, 이 함수 안에서 불러온다
	(테스트가 .env 없이도 extract_indicators의 나머지 로직을 확인할 수 있게 하려는 것).
	"""
	from hri.llm.llm_client import get_chat_model

	model = get_chat_model(max_tokens=INDICATOR_MAX_TOKENS).with_structured_output(IndicatorList)
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