"""관리자 대시보드 · build_admin_tab, on_refresh, get_dashboard_data, get_dashboard_data_v2, plot_daily_counts (임세준)

관리자 계정에만 보이는 대시보드 화면.
- get_dashboard_data(): 대시보드 1차 숫자를 모아 화면 형식(마크다운 표)으로 가공 (3.7.8)
- build_admin_tab(): 사용 현황·답변 품질·성능 비용·문서 관리·운영 상태 화면과 새로고침 버튼 배치 (3.7.9, 2차 화면 3.7.12)
- on_refresh(): 새로고침 버튼을 누르면 get_dashboard_data_v2() 결과로 화면을 갱신 (3.7.9, 2차 화면 3.7.12)
- plot_daily_counts(): 일별 질문 수·평균 응답 시간 선 그래프를 PNG로 저장 (3.7.11)
- get_dashboard_data_v2(): 1차 데이터에 일별 추이 차트·페르소나 비율·처리 방식 비율·피드백 비율·근거 없는 질문 목록을 더해 가공 (3.7.11)
"""
import uuid

import gradio as gr

from hri.dao.dashboard_dao import (
	select_daily_counts,
	select_feedback_ratio,
	select_no_source_questions,
	select_perf_cost,
	select_persona_ratio,
	select_recent_errors,
	select_route_ratio,
	select_source_ratio,
	select_top_questions
)
from hri.domain.schemas import DashboardData
from hri.llm.llm_client import cost_korean_won, get_usd_krw
from hri.loader.table_loader import table_to_markdown
from hri.service.indicator_service import PLOT_DIR, _use_korean_font
from hri.service.report_service import search_reports
from hri.util.logger import safe_call

# 기록이 없는 표 대신 보여 줄 문구
NO_STATS_MESSAGE = "기록된 통계가 없습니다."

# app.py가 관리자 탭의 업로드 버튼 click을 연결할 때 쓰는 컴포넌트 모음 (upload_components와 같은 방식)
admin_components = {}


def _table_or_message(table: str | None) -> str:
	"""
	표에 기록이 없으면 안내 문구로 바꾸기

	table_to_markdown()이 만든 표가 머리글·구분선 두 줄뿐이면(기록 없음) '기록된 통계가 없습니다.'를,
	기록이 있으면 표를 그대로 돌려준다.

	입력: table (마크다운 표)
	출력: str (표 또는 안내 문구)
	"""
	if table == None or table.count("\n") <= 1:
		return NO_STATS_MESSAGE
	return table

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


def build_admin_tab():
	"""
	관리자 대시보드 화면 만들기

	사용 현황·답변 품질·성능 비용·문서 관리·운영 상태를
	gr.Markdown(표)·gr.Image(차트)로 구성하고 새로고침 gr.Button을 둔다.

	구역별 화면 (1차 + 2차)
	- 사용 현황: 질문 TOP 10 표, 일별 질문 수 추이 차트, 페르소나별 사용 비율 표, 처리 방식(보고서 근거 답변·자료에 없음·잡담·오류)별 비율 표
	- 답변 품질: '자료에 없습니다' 응답 비율, 👍/👎 피드백 비율 표, 근거 없는 질문 목록 표
	- 성능·비용: 평균 응답 시간·원화 비용 합계, flow별 토큰 표
	- 문서 관리: 보고서 목록 표
	- 운영 상태: 최근 에러 로그 표

	- 관리자 계정에만 보이도록 처음에는 숨겨 둔다 (visible=False, 관리자가 로그인하면 on_login이 보이게 함)
	- 새로고침 버튼은 state가 필요 없어서 여기서 바로 on_refresh()와 연결한다
	- 새로고침 버튼은 화면 오른쪽 위에 둔다
	- 표마다 작은 제목(####)을 붙이고, 같은 구역의 표는 gr.Row·gr.Column으로 나란히 둔다 (차트는 높이 480으로 넓게)
	- 관리자 탭이 선택되면(관리자가 로그인하면 on_login이 이 탭을 선택함) 새로고침을 누르지 않아도 on_refresh()로 바로 채운다
	- 차트(gr.Image)와 차트 안내 문구는 로그인 전에는 보이지 않는다 (관리자 탭이 선택되어 갱신되면 차트가 있을 때는 차트를, 없을 때는 '일별 질문 수: 표시할 데이터가 없습니다.'를 보여 줌)

	입력: 없음
	출력: gr.Tab (관리자 탭)
	"""
	with gr.Tab("관리자", id="admin", visible=False) as admin_tab:
		# 오른쪽 위 새로고침 버튼 (제목은 왼쪽, 버튼은 오른쪽 끝)
		with gr.Row(equal_height=True):
			gr.Markdown("## 관리자 대시보드")
			refresh_btn = gr.Button("새로고침", variant="primary", scale=0, min_width=120)

		# 사용 현황 (표 3개는 한 줄에 나란히, 차트는 아래에 넓게)
		gr.Markdown("### 사용 현황")
		with gr.Row():
			with gr.Column():
				gr.Markdown("#### 질문 TOP 10")
				top_questions = gr.Markdown()
			with gr.Column():
				gr.Markdown("#### 페르소나별 사용 비율")
				persona_ratio = gr.Markdown()
			with gr.Column():
				gr.Markdown("#### 처리 방식별 비율")
				route_ratio = gr.Markdown()
		daily_chart = gr.Image(label="일별 질문 수·평균 응답 시간", interactive=False, visible=False, height=480)
		daily_chart_message = gr.Markdown()

		# 답변 품질 (응답 비율은 위에, 표 2개는 나란히)
		gr.Markdown("### 답변 품질")
		source_ratio = gr.Markdown()
		with gr.Row():
			with gr.Column():
				gr.Markdown("#### 👍/👎 피드백 비율")
				feedback_ratio = gr.Markdown()
			with gr.Column():
				gr.Markdown("#### 근거 없는 질문 (보고서 보강 후보)")
				no_source_questions = gr.Markdown()

		# 성능·비용
		gr.Markdown("### 성능·비용")
		perf_cost = gr.Markdown()
		gr.Markdown("#### flow별 토큰·원화 비용")
		usage_by_flow = gr.Markdown()

		# 문서 관리·운영 상태 (나란히)
		with gr.Row():
			with gr.Column():
				gr.Markdown("### 문서 관리")
				gr.Markdown("#### 보고서 업로드")
				upload_file = gr.File(label="보고서 PDF", file_types=[".pdf"], file_count="multiple", type="filepath")
				upload_btn = gr.Button("업로드", variant="primary")
				upload_result = gr.Markdown()
				gr.Markdown("#### 보고서 목록")
				reports = gr.Markdown()
			with gr.Column():
				gr.Markdown("### 운영 상태")
				gr.Markdown("#### 최근 에러 로그")
				recent_errors = gr.Markdown()

	# on_refresh()가 돌려주는 순서와 같게, 화면 위에서 아래 순서
	outputs = [
		top_questions, daily_chart, daily_chart_message, persona_ratio, route_ratio,
		source_ratio, feedback_ratio, no_source_questions,
		perf_cost, usage_by_flow,
		reports,
		recent_errors
	]

	# 새로고침 버튼 누르면 대시보드 갱신
	refresh_btn.click(fn=on_refresh, outputs=outputs)

	# 관리자 탭이 선택되면(로그인하면 자동 선택됨) 버튼을 누르지 않아도 바로 갱신
	admin_tab.select(fn=on_refresh, outputs=outputs)

	# 업로드 버튼은 state·다른 탭 드롭다운이 필요해서 app.py에서 on_upload()와 연결한다
	admin_components.update(file=upload_file, upload_btn=upload_btn, result=upload_result, outputs=outputs)

	return admin_tab


@safe_call
def on_refresh():
	"""
	새로고침 버튼 눌렀을 때

	get_dashboard_data_v2() 결과(1차 + 2차 데이터)로 대시보드 컴포넌트를 갱신한다.

	- 표(질문 TOP 10·페르소나 비율·처리 방식 비율·피드백 비율·근거 없는 질문·flow별 토큰·보고서 목록·최근 에러)는 마크다운 표 그대로 보여 준다
	- 자료 유무 응답 비율은 %로, 평균 응답 시간은 ms로, 원화 비용 합계는 원으로 보여 준다
	- 일별 질문 수 차트
	  - 차트가 있으면: 이미지 칸을 보이게 하고 차트를 넣고, 안내 문구는 지운다
	  - 차트가 없으면(기록이 없음): 이미지 칸을 숨기고 '일별 질문 수: 표시할 데이터가 없습니다.'를 보여 준다
	  - 돌려주는 값 12개는 build_admin_tab()의 outputs 순서와 같아야 한다
	  [질문 TOP 10, 일별 차트, 차트 안내 문구, 페르소나 비율, 처리 방식 비율,
	   자료 유무 비율, 피드백 비율, 근거 없는 질문,
	   응답 시간·원화 비용, flow별 토큰, 보고서 목록, 최근 에러]

	입력: 없음
	출력: tuple (값 12개)
	"""
	data = get_dashboard_data_v2()

	# 숫자는 단위를 붙여서 보여줌
	source_ratio = f"'자료에 없습니다' 응답 비율: **{round(data.source_ratio * 100, 1)}%**"
	perf_cost = f"평균 응답 시간: **{data.avg_response_ms} ms** / 원화 비용 합계: **{round(data.cost_krw, 2)}원**"

	# 일별 질문 수 차트 (없으면 안내 문구)
	if data.daily_chart != None:
		daily_chart = gr.update(value=data.daily_chart, visible=True)
		daily_chart_message = ""
	else:
		daily_chart = gr.update(value=None, visible=False)
		daily_chart_message = "일별 질문 수: 표시할 데이터가 없습니다."

	return (
		_table_or_message(data.top_questions),
		daily_chart,
		daily_chart_message,
		_table_or_message(data.persona_ratio),
		_table_or_message(data.route_ratio),
		source_ratio,
		_table_or_message(data.feedback_ratio),
		_table_or_message(data.no_source_questions),
		perf_cost,
		_table_or_message(data.usage_by_flow),
		_table_or_message(data.reports),
		_table_or_message(data.recent_errors)
	)


def plot_daily_counts(rows: list[dict]) -> str:
	"""
	일별 추이 차트 그리기

	matplotlib 선 그래프로 일별 질문 수와 평균 응답 시간을 위아래 두 그래프로 나눠 그려 PNG 한 장으로 저장한다.

	순서
	1. rows를 날짜(가로축)·질문 수·평균 응답 시간 리스트로 나눈다
	   (평균 응답 시간이 None인 날은 float("nan")으로 바꿔 그 날만 선을 끊어서 그린다)
	2. 한글 글꼴을 정한다 (장유빈 님 _use_korean_font() 재사용, 못 찾으면 기본 글꼴)
	3. 위 그래프에 질문 수(건), 아래 그래프에 평균 응답 시간(ms)을 선으로 그린다
	   (한 그래프에 두 선을 그리면 날짜가 적을 때 선이 겹쳐 보여서 나눔, 가로축 날짜는 두 그래프가 함께 씀)
		(질문 수는 건수라서 세로축 눈금을 정수로만 표시)
	4. data/plots/에 daily_uuid.png로 저장하고 그림을 닫는다 (지표 비교 차트와 같은 폴더)

	- 화면 없는 서버에서도 그릴 수 있게 matplotlib.use("Agg")를 쓴다
	- 기록이 없을 때는 부르지 않는다 (get_dashboard_data_v2()가 rows가 있을 때만 부름)

	입력: rows (select_daily_counts() 결과, 예: [{'day': date(2026, 10, 27), 'question_count': 2, 'avg_response_ms': 1500.0}, ...])
	출력: str (저장한 PNG 파일 경로)
	"""
	import matplotlib

	matplotlib.use("Agg")
	import matplotlib.pyplot as plt
	from matplotlib.ticker import MaxNLocator

	# 1) 가로축(날짜)·세로축(질문 수, 평균 응답 시간) 값 나누기
	days = []
	counts = []
	avg_ms = []
	for row in rows:
		days.append(str(row["day"]))
		counts.append(row["question_count"])
		if row["avg_response_ms"] == None:
			avg_ms.append(float("nan"))
		else:
			avg_ms.append(row["avg_response_ms"])

	# 2) 한글 글꼴 (못 찾으면 기본 글꼴)
	font = _use_korean_font()
	if font != None:
		plt.rcParams["font.family"] = font
	plt.rcParams["axes.unicode_minus"] = False

	# 3) 선 그래프 그리기 (위: 질문 수, 아래: 평균 응답 시간, 가로축 날짜는 함께 씀)
	fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True, layout="constrained")

	ax1.plot(days, counts, marker="o", color="C0")
	ax1.set_title("일별 질문 수")
	ax1.set_ylabel("질문 수 (건)")
	ax1.yaxis.set_major_locator(MaxNLocator(integer=True))

	ax2.plot(days, avg_ms, marker="s", color="C1")
	ax2.set_title("일별 평균 응답 시간")
	ax2.set_ylabel("평균 응답 시간 (ms)")
	ax2.set_xlabel("날짜")
	ax2.tick_params(axis="x", rotation=45)

	# 4) PNG로 저장하고 그림 닫기
	PLOT_DIR.mkdir(parents=True, exist_ok=True)
	path = PLOT_DIR / f"daily_{uuid.uuid4().hex}.png"
	fig.savefig(path, dpi=150)
	plt.close(fig)

	return str(path)


def get_dashboard_data_v2() -> DashboardData:
	"""
	대시보드 2차 데이터 만들기

	일별 질문 수, 페르소나별 사용 비율, 피드백 비율, 근거 없는 질문 목록을 대시보드 화면 형식에 맞게 가공한다.
	(잡담[chat]·오류[error]는 qa_logs.route로 답변 품질 통계에서 제외)

	순서
	1. get_dashboard_data()로 1차 데이터를 만든다 (DashboardData 하나에 1차·2차를 함께 담으려고)
	2. 일별 질문 수: 기록이 있으면 plot_daily_counts()로 추이 차트를 그려 경로를 담는다 (없으면 None)
	3. 페르소나별 사용 비율: [페르소나, 질문 수, 비율] 표 (맨 아래 ROLLUP 합계 줄은 '합계')
	   처리 방식별 비율: [처리 방식, 질문 수, 비율] 표 (route를 한글 이름으로 바꿈, 맨 아래 합계 줄은 '합계')
	4. 피드백 비율: [구분, 건수, 비율] 표 (👍·👎·합계)
	5. 근거 없는 질문 목록: [질문, '자료에 없습니다' 횟수] 표

	- 잡담·오류 제외: 답변 품질 통계(피드백 비율·근거 없는 질문)는 SQL에서 이미 rag·no_answer만 센다
	  페르소나별 사용 비율·처리 방식별 비율은 사용 현황이라 모든 질문(잡담·오류 포함)을 센다
	- 비율은 %로, 소수 첫째 자리까지 보여 준다
	- 기록이 없으면 표는 머리글만, 차트는 None

	입력: 없음
	출력: DashboardData (1차 칸 + 2차 칸)
	"""
	# 1) 1차 데이터
	data = get_dashboard_data()

	# 2) 일별 질문 수 → 추이 차트 (기록이 있을 때만)
	daily_rows = select_daily_counts()
	if len(daily_rows) > 0:
		data.daily_chart = plot_daily_counts(daily_rows)

	# 3) 페르소나별 사용 비율 (맨 아래 줄이 합계)
	persona_rows = select_persona_ratio()

	total = 0
	for row in persona_rows:
		if row["persona"] == None:
			total = row["count"]

	persona_table = [["페르소나", "질문 수", "비율"]]
	for row in persona_rows:
		if row["persona"] == None:
			persona_table.append(["합계", row["count"], ""])
		else:
			ratio = round(row["count"] / total * 100, 1)
			persona_table.append([row["persona"], row["count"], f"{ratio}%"])
	data.persona_ratio = table_to_markdown(persona_table)
	
	# 3-2) 처리 방식(route)별 비율 (맨 아래 줄이 합계)
	route_names = {
		"rag": "보고서 근거 답변 (rag)",
		"no_answer": "자료에 없음 (no_answer)",
		"chat": "잡담 (chat)",
		"error": "오류 (error)"
	}
	route_rows = select_route_ratio()

	route_total = 0
	for row in route_rows:
		if row["route"] == None:
			route_total = row["count"]

	route_table = [["처리 방식", "질문 수", "비율"]]
	for row in route_rows:
		if row["route"] == None:
			route_table.append(["합계", row["count"], ""])
		else:
			ratio = round(row["count"] / route_total * 100, 1)
			route_table.append([route_names.get(row["route"], row["route"]), row["count"], f"{ratio}%"])
	data.route_ratio = table_to_markdown(route_table)

	# 4) 피드백 비율 (피드백이 있을 때만 줄 추가)
	feedback = select_feedback_ratio()

	feedback_table = [["구분", "건수", "비율"]]
	if feedback["total"] > 0:
		feedback_table.append(["👍", feedback["up_count"], f"{round(feedback['up_ratio'] * 100, 1)}%"])
		feedback_table.append(["👎", feedback["down_count"], f"{round(feedback['down_ratio'] * 100, 1)}%"])
		feedback_table.append(["합계", feedback["total"], ""])
	data.feedback_ratio = table_to_markdown(feedback_table)

	# 5) 근거 없는 질문 목록
	no_source_table = [["질문", "'자료에 없습니다' 횟수"]]
	for row in select_no_source_questions():
		no_source_table.append([row["question"], row["count"]])
	data.no_source_questions = table_to_markdown(no_source_table)

	return data