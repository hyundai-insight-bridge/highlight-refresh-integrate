"""관리자 대시보드 · build_admin_tab, on_refresh, get_dashboard_data, get_dashboard_data_v2, plot_daily_counts (임세준)

관리자 계정에만 보이는 대시보드 화면.
- get_dashboard_data(): 대시보드 1차 숫자를 모아 화면 형식(마크다운 표)으로 가공 (3.7.8)
"""
from hri.dao.dashboard_dao import select_perf_cost, select_recent_errors, select_source_ratio, select_top_questions
from hri.domain.schemas import DashboardData
from hri.llm.llm_client import cost_korean_won, get_usd_krw
from hri.loader.table_loader import table_to_markdown
from hri.service.report_service import search_reports


def get_dashboard_data() -> DashboardData:
	"""
	대시보드 1차 데이터 만들기

	질문 TOP 10·자료 유무 응답 비율(route가 rag·no_answer인 것만)·평균 응답 시간·flow별 토큰·원화 비용(llm_usage)·
	보고서 목록·최근 에러 로그를 table_to_markdown()으로 화면 형식에 맞게 가공한다.

	순서
	1. 질문 TOP 10을 [질문, 횟수] 표로 만든다
	2. 자료 유무 응답 비율('자료에 없습니다' 비율)을 가져온다
	3. select_perf_cost()의 일자별 평균 응답 시간을 날짜마다 한 번씩만 모아 평균을 낸다
	4. select_perf_cost()의 토큰을 flow·모델별로 더하고, cost_korean_won()으로 flow별 원화 비용을 계산해
	   [flow, 입력 토큰, 출력 토큰, 원화 비용] 표와 원화 비용 합계를 만든다
	5. 보고서 목록을 [제목, 발행일, 청크 수] 표로 만든다
	6. 최근 에러 로그를 [시각, 사용자, 질문, 에러] 표로 만든다
	7. DashboardData에 담아 돌려준다

	- 원화 비용은 DB에 저장하지 않고 여기서 계산해 대시보드에만 보여 준다 (환율은 get_usd_krw())
	- 기록이 없으면 표는 머리글만, 숫자는 0.0

	입력: 없음
	출력: DashboardData
	"""
	# 1) 질문 TOP 10
	top_rows = [["질문", "횟수"]]
	for row in select_top_questions():
		top_rows.append([row["question"], row["count"]])

	# 2) 자료 유무 응답 비율
	source_ratio = select_source_ratio()

	# 3) 평균 응답 시간 (같은 날짜가 flow·모델 수만큼 반복되므로 날짜별로 한 번만 모음)
	perf_rows = select_perf_cost()

	day_avg = {}
	for row in perf_rows:
		if row["avg_response_ms"] != None:
			day_avg[row["day"]] = row["avg_response_ms"]

	avg_response_ms = 0.0
	if len(day_avg) > 0:
		total_ms = 0.0
		for ms in day_avg.values():
			total_ms = total_ms + ms
		avg_response_ms = round(total_ms / len(day_avg), 1)

	# 4) flow별 토큰·원화 비용
	# flow → 모델 → 토큰 수 (같은 모델이 여러 날짜에 있으면 더함)
	# 예) {"qa": {"gpt-5-mini-2025-08-07": {"input_tokens": 1200, "output_tokens": 300}}}
	usage_by_flow = {}
	for row in perf_rows:
		flow = row["flow"]
		model = row["model"]

		if flow not in usage_by_flow:
			usage_by_flow[flow] = {}
		if model not in usage_by_flow[flow]:
			usage_by_flow[flow][model] = {"input_tokens": 0, "output_tokens": 0}

		usage_by_flow[flow][model]["input_tokens"] = usage_by_flow[flow][model]["input_tokens"] + row["input_tokens"]
		usage_by_flow[flow][model]["output_tokens"] = usage_by_flow[flow][model]["output_tokens"] + row["output_tokens"]

	usd_krw = get_usd_krw()

	usage_rows = [["flow", "입력 토큰", "출력 토큰", "원화 비용"]]
	cost_krw = 0.0
	for flow, usage in usage_by_flow.items():
		# flow 안의 모델 토큰 더하기
		input_tokens = 0
		output_tokens = 0
		for tokens in usage.values():
			input_tokens = input_tokens + tokens["input_tokens"]
			output_tokens = output_tokens + tokens["output_tokens"]

		# 모델마다 단가가 달라서 모델별 토큰을 그대로 넘겨 원화 계산
		cost = cost_korean_won(usage, usd_krw)
		cost_krw = cost_krw + cost

		usage_rows.append([flow, input_tokens, output_tokens, f"{round(cost, 2)}원"])

	cost_krw = round(cost_krw, 4)

	# 5) 보고서 목록
	report_rows = [["제목", "발행일", "청크 수"]]
	for report in search_reports():
		report_rows.append([report.title, report.published_date, report.chunk_count])

	# 6) 최근 에러 로그
	error_rows = [["시각", "사용자", "질문", "에러"]]
	for row in select_recent_errors():
		error_rows.append([row["created_at"], row["user_id"], row["question"], row["error"]])

	# 7) 화면에 보여 줄 형식으로 담기
	return DashboardData(
		top_questions=table_to_markdown(top_rows),
		source_ratio=source_ratio,
		avg_response_ms=avg_response_ms,
		usage_by_flow=table_to_markdown(usage_rows),
		cost_krw=cost_krw,
		reports=table_to_markdown(report_rows),
		recent_errors=table_to_markdown(error_rows)
	)