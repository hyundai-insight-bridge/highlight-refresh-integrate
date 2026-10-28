"""Tool Calling · TOOLS, run_agent_with_tools (김희진)"""

# 에이전트 그래프(agent_graph)가 TOOLS를 bind_tools·ToolNode로 쓴다.
# 서비스 함수는 모두 도구 안에서 import한다: 서비스가 graph/registry를 import하므로 순환 import를 막고,

import json
import logging
from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from hri.exception.errors import ExternalApiError, OutputFormatError

__all__ = ["TOOLS"]

logger = logging.getLogger(__name__)

# 선택한 보고서가 없을 때 도구가 돌려주는 안내
NO_REPORTS_MESSAGE = "선택한 보고서가 없습니다. 보고서를 선택한 뒤 다시 요청해 주세요."
# 서비스 함수가 아직 없을 때 도구가 돌려주는 안내 (모델이 다른 방법을 안내하거나 처리 불가를 답한다)
NOT_IMPLEMENTED_MESSAGE = "[미구현] {name} 기능을 아직 사용할 수 없습니다."
# 통계를 찾지 못했을 때 안내
NO_ECOS_QUERY_MESSAGE = "보고서 지표와 비교할 ECOS 통계를 찾지 못했습니다."
NO_ECOS_DATA_MESSAGE = "조건에 맞는 ECOS 통계 값이 없습니다."
NO_EXCHANGE_RATE_MESSAGE = "환율을 불러오지 못했습니다."
# ECOS 라이브러리 등 예상 못 한 오류가 났을 때 안내 (오류 내용은 로그에만 남긴다)
ECOS_FAIL_MESSAGE = "데이터를 불러오지 못했습니다."

# report_ids는 LLM이 아니라 그래프 상태(AgentState.report_ids)에서 주입한다 (LLM이 보고서를 고르거나 바꾸지 못함)
ReportIds = Annotated[list[int], InjectedState("report_ids")]


def _dump(model) -> dict:
	"""Pydantic 모델 1개를 JSON으로 바꿀 수 있는 dict로 만든다."""
	return model.model_dump(mode="json")


def _to_json(data) -> str:
	"""dict·list를 한글이 깨지지 않는 JSON 문자열로 만든다 (도구 반환값은 문자열이어야 한다)."""
	return json.dumps(data, ensure_ascii=False)


@tool
def summarize_reports(report_ids: ReportIds) -> str:
	"""선택한 보고서마다 3줄 요약과 섹션별 요약을 만든다. 보고서 내용을 요약해 달라는 요청에 쓴다."""
	if not report_ids:
		return NO_REPORTS_MESSAGE

	from hri.service.summary_service import summarize_report

	results = []
	for report_id in report_ids:
		try:
			results.append({"report_id": report_id, "summary": _dump(summarize_report(report_id))})
		except OutputFormatError:
			logger.exception("도구 요약 실패: report_id=%s", report_id)
			results.append({"report_id": report_id, "error": "요약을 만들지 못했습니다."})
	return _to_json(results)


@tool
def verify_and_expand(request: str, report_ids: ReportIds) -> str:
	"""보고서의 수치·전망을 한국은행 ECOS 최신 통계와 비교해 일치·차이를 확인하고, 근거가 부족한 부분을 보완한다.

	request에는 사용자가 확인하려는 내용(예: '성장률 전망이 맞는지')을 그대로 적는다.
	"""
	if not report_ids:
		return NO_REPORTS_MESSAGE

	try:
		from hri.prompt.summary_prompt import verify_and_expand as run_verify
	except ImportError:
		logger.error(NOT_IMPLEMENTED_MESSAGE.format(name="verify_and_expand"))
		return NOT_IMPLEMENTED_MESSAGE.format(name="검증·보완")

	results = []
	for report_id in report_ids:
		try:
			results.append({"report_id": report_id, "result": _dump(run_verify(report_id, request))})
		except (OutputFormatError, ExternalApiError) as e:
			logger.exception("도구 검증 실패: report_id=%s", report_id)
			results.append({"report_id": report_id, "error": getattr(e, "user_message", "검증하지 못했습니다.")})
	return _to_json(results)


@tool
def merge_reports(report_ids: ReportIds) -> str:
	"""선택한 보고서 2개 이상을 공통 의견·차이점·종합 결론으로 병합한다. 여러 보고서를 합쳐 정리해 달라는 요청에 쓴다."""
	if not report_ids:
		return NO_REPORTS_MESSAGE

	try:
		from hri.prompt.summary_prompt import merge_reports as run_merge
	except ImportError:
		logger.error(NOT_IMPLEMENTED_MESSAGE.format(name="merge_reports"))
		return NOT_IMPLEMENTED_MESSAGE.format(name="보고서 병합")

	try:
		return _to_json(_dump(run_merge(report_ids)))
	except OutputFormatError:
		logger.exception("도구 병합 실패: report_ids=%s", report_ids)
		return "보고서를 병합하지 못했습니다."


@tool
def find_usable_data(question: str, report_ids: ReportIds) -> str:
	"""선택한 보고서의 지표 가운데 ECOS 통계로 확인할 수 있는 지표 1개와 통계표 조회 조건(통계표 코드·주기·항목코드·기간)을 찾는다.

	question에는 사용자가 확인하려는 내용을 적는다. 결과의 조회 조건은 get_ecos_statistic_data에 그대로 넘긴다.
	"""
	if not report_ids:
		return NO_REPORTS_MESSAGE
	logger.debug("ECOS 활용 데이터 판단 요청: %s", question)

	from hri.api.ecos_finder import find_usable_data as run_find
	from hri.service.indicator_service import extract_indicators

	try:
		indicators = [ind for report_id in report_ids for ind in extract_indicators(report_id)]
		query = run_find(indicators) if indicators else None
	except ExternalApiError as e:
		logger.exception("도구 ECOS 판단 실패")
		return e.user_message
	except Exception:
		logger.exception("도구 ECOS 판단 오류")
		return ECOS_FAIL_MESSAGE
	return _to_json(_dump(query)) if query else NO_ECOS_QUERY_MESSAGE


@tool
def get_ecos_statistic_data(
	stat_code: str,
	cycle: Literal["A", "Q", "M", "D"],
	item_code: str,
	start: str,
	end: str,
	item_code2: str | None = None,
	indicator_name: str = "",
) -> str:
	"""한국은행 ECOS 통계 값을 조회한다. find_usable_data가 돌려준 통계표 코드·주기·항목코드·기간을 그대로 넣는다.

	start·end는 주기와 같은 형식이다 (A: 2025, Q: 2026Q1, M: 202607, D: 20261023).
	indicator_name에는 비교할 보고서 지표 이름을 적는다.
	"""
	from hri.api.ecos_client import fetch_indicators
	from hri.domain.schemas import EcosQuery

	query = EcosQuery(
		stat_code=stat_code, cycle=cycle, item_code=item_code, item_code2=item_code2,
		start=start, end=end, indicator_name=indicator_name,
	)
	try:
		indicators = fetch_indicators(query, indicator_name or stat_code)
	except ExternalApiError as e:
		logger.exception("도구 ECOS 조회 실패: %s", stat_code)
		return e.user_message
	except Exception:
		logger.exception("도구 ECOS 조회 오류: %s", stat_code)
		return ECOS_FAIL_MESSAGE
	return _to_json([_dump(ind) for ind in indicators]) if indicators else NO_ECOS_DATA_MESSAGE


@tool
def get_ecos_exchange_rate(currency: Literal["USD", "JPY", "EUR"]) -> str:
	"""한국은행 ECOS의 가장 최근 일별 환율(원화 기준)과 기준일을 조회한다. JPY는 100엔당 원화다."""
	from hri.api.ecos_client import get_exchange_rates

	try:
		rates = get_exchange_rates([currency])
	except ExternalApiError as e:
		logger.exception("도구 환율 조회 실패: %s", currency)
		return e.user_message
	except Exception:
		logger.exception("도구 환율 조회 오류: %s", currency)
		return ECOS_FAIL_MESSAGE
	return _to_json([_dump(rate) for rate in rates]) if rates else NO_EXCHANGE_RATE_MESSAGE


# agent_graph.load_tools()가 이 목록을 가져다 bind_tools·ToolNode에 쓴다
TOOLS = [
	summarize_reports,
	verify_and_expand,
	merge_reports,
	find_usable_data,
	get_ecos_statistic_data,
	get_ecos_exchange_rate,
]