"""환율 패널·지표 비교 · build_indicator_panel (류현수) / on_compare (장유빈)"""
import logging

import gradio as gr

from hri.service.indicator_service import build_compare_table, build_ecos_reference, plot_indicators

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# [장유빈] 지표 비교 · on_compare
# ---------------------------------------------------------------------
MIN_COMPARE_REPORTS = 2
NEED_MORE_REPORTS_MESSAGE = "보고서를 2개 이상 선택하세요."
NO_INDICATORS_MESSAGE = "선택한 보고서에서 비교할 지표를 찾지 못했습니다."
NO_CHART_NOTE = "공통으로 나온 지표가 없어 차트는 만들지 않았습니다."
COMPARE_ERROR_MESSAGE = "지표를 비교하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
ECOS_PROGRESS_TEXT = "ECOS 통계를 확인하는 중..."


def on_compare(report_ids: list[int] | None, progress=gr.Progress()) -> tuple[str, str | None]:
	"""선택한 보고서들의 지표를 비교해 (Markdown 표, 차트 이미지 경로)를 돌려준다.

	보고서가 2개 미만이면 안내 문구만 보여 준다. 2개 이상이면 build_compare_table()과 plot_indicators()를 부르고,
	처리 중에는 진행 표시를 한다. 지표가 없으면 안내 문구를, 공통 지표가 없어 차트를 못 그리면 표 아래에 안내를 붙인다.
	처리 중 예외가 나면 오류 안내 문구를 보여 준다. 차트가 없으면 이미지 자리는 None이다.
	"""
	ids = list(dict.fromkeys(int(i) for i in (report_ids or [])))
	if len(ids) < MIN_COMPARE_REPORTS:
		return NEED_MORE_REPORTS_MESSAGE, None

	try:
		progress(0.1, desc="보고서에서 지표를 읽는 중...")
		table = build_compare_table(ids)
		if not table:
			return NO_INDICATORS_MESSAGE, None
		progress(0.7, desc="차트를 그리는 중...")
		image = plot_indicators(ids)
	except Exception:
		logger.exception("지표 비교 중 오류")
		return COMPARE_ERROR_MESSAGE, None

	if image is None:
		table = f"{table}\n\n{NO_CHART_NOTE}"

	progress(0.9, desc=ECOS_PROGRESS_TEXT)
	ecos = _safe_ecos_reference(ids)
	if ecos:
		table = f"{table}\n\n{ecos}"
	return table, image


def _safe_ecos_reference(report_ids: list[int]) -> str:
	"""ECOS 참고 섹션을 만든다. 실패해도 비교표는 보여 줘야 하므로 오류는 기록만 하고 빈 문자열을 돌려준다."""
	try:
		return build_ecos_reference(report_ids)
	except Exception:
		logger.exception("ECOS 참고 섹션 생성 실패")
		return ""