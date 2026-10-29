"""메인 화면 · build_app, main, init_state (임세준)

앱의 전체 화면 틀을 만들고 실행하는 파일.
각 담당자가 만든 탭 함수를 불러와서 하나의 화면으로 합친다.
실행: 프로젝트 맨 위 폴더에서 python app.py
"""

import uuid
import gradio as gr

from hri.config.settings import load_settings
from hri.graph.registry import get_ingest_graph, get_qa_graph, get_summary_graph, get_agent_graph
from hri.view.user_view import build_login_tab, on_login, on_logout, login_components
from hri.view.report_view import build_upload_tab, build_report_list_panel, on_view_summary, on_go_chat, on_report_select, on_upload, report_list_components, upload_components
from hri.view.summary_view import build_summary_tab, on_summarize, on_request, summary_components
from hri.view.chat_view import build_chat_tab, chat_components, connect_chat_events, refresh_report_choices
from hri.view.indicator_view import on_compare
from hri.view.history_view import build_history_tab, history_components, on_load_history, on_restore
from hri.view.admin_view import build_admin_tab


def init_state():
	"""
	처음 상태(gr.State에 넣을 값) 만들기

	로그인 전 화면에서 쓰는 빈 상태를 만든다.
	- user: 로그인한 사람 정보 (로그인 전에는 None)
	- session_id: 대화 묶음 번호 (uuid4로 새로 만듦)
	- report_ids: 선택한 보고서 번호 목록 (처음에는 빈 리스트)
	- last_log_id: 마지막 질문 기록 번호 (처음에는 None)

	입력: 없음
	출력: dict (위 4개 키를 가진 딕셔너리)
	"""
	state = {
		"user": None,
		"session_id": str(uuid.uuid4()),
		"report_ids": [],
		"last_log_id": None
	}
	return state


def build_app():
	"""
	메인 화면 만들기

	gr.Blocks 안에 제목·로그아웃 버튼과 탭 6개를 gr.Tabs로 배치한다.
	- 로그인 탭: build_login_tab() (처음에는 이 탭만 보임)
	- 보고서 탭: 안에 작은 탭 3개
		- 보고서 목록·검색: build_report_list_panel()
		- 지표 비교표: 비교할 보고서 드롭다운 + 비교 버튼 + 비교표 + 차트
		- 업로드: build_upload_tab()
	- 요약·분석, 질의응답, 내 기록, 관리자 탭: 각 담당자의 build_*_tab()
	  (로그인 전에는 숨김, 관리자 탭은 관리자만 보임)

	버튼 연결
	- 로그인 버튼 → on_login (탭 보이기, 로그아웃 버튼 보이기, 질의응답 탭 선택, 비교 보고서 목록 채우기)
	- 로그아웃 버튼 → on_logout (로그인 탭만 남기기)
	- 요약 보기 · 질의응답으로 이동 버튼 → on_view_summary · on_go_chat (탭 이동 + 보고서 드롭다운 바꾸기)
	- 지표 추출·비교 버튼 → on_compare (비교표, 차트 보여주기)
	- 업로드 버튼 → on_upload (진행 상황·결과 보여주기, 요약·질의응답 탭 보고서 드롭다운 갱신)
	- 요약·분석 탭을 열면 → refresh_report_choices (보고서 드롭다운 채우기, 질의응답 탭과 같은 함수)
	- 요약하기 버튼 → on_summarize (선택한 보고서 요약 보여주기)
	- 요청 실행 버튼 → on_request (자연어 요청 결과·실행한 도구 보여주기)
	  (업로드·요약 버튼은 다른 탭의 드롭다운이나 state가 필요해서 모든 탭을 만든 뒤 여기서 연결한다)
	- 내 기록 탭을 열면 → on_load_history (대화별 기록 표·대화 선택 목록 채우기)

	입력: 없음
	출력: gr.Blocks (만든 화면)
	"""
	with gr.Blocks(title="HRI Insight Bridge") as demo:
		state = gr.State(init_state())

		# 제목, 로그아웃 버튼 (로그아웃 버튼은 처음에 숨김)
		with gr.Row():
			gr.Markdown("## 📊 HRI Insight Bridge - 경제분석보고서 AI 요약·질의응답")
			logout_btn = gr.Button("로그아웃", size="sm", scale=0, visible=False)

		with gr.Tabs(selected="login") as tabs:
			# 로그인 탭
			login_tab = build_login_tab()

			# 보고서 탭
			with gr.Tab("보고서", id="report", visible=False) as report_tab:
				with gr.Tabs():
					# 보고서 목록·검색
					with gr.Tab("보고서 목록·검색", id="report_list"):
						report_list, go_summary_btn, go_chat_btn = build_report_list_panel()

					# 지표 비교표
					with gr.Tab("지표 비교표", id="compare"):
						compare_reports = gr.Dropdown(label="비교할 보고서(2개 이상)", choices=[], multiselect=True)
						compare_btn = gr.Button("지표 추출·비교", variant="primary")
						compare_table = gr.Markdown()
						compare_chart = gr.Image(label="비교 차트")

					# 보고서 업로드
					build_upload_tab()

			# 요약·분석, 질의응답, 내 기록, 관리자 탭
			summary_tab = build_summary_tab()
			chat_tab = build_chat_tab()
			# 질의응답 탭 버튼 연결 (state가 필요해서 build_app에서 부름)
			connect_chat_events(state)
			history_tab = build_history_tab()
			admin_tab = build_admin_tab()

		# 로그인 버튼 누르면 로그인
		login_components["login_btn"].click(
			fn=on_login,
			inputs=[login_components["user_id"], login_components["password"]],
			outputs=[state, login_tab, report_tab, summary_tab, chat_tab, history_tab, admin_tab, logout_btn, tabs, compare_reports, login_components["message"]]
		)

		# 로그아웃 버튼 누르면 로그아웃
		logout_btn.click(
			fn=on_logout,
			inputs=state,
			outputs=[state, login_tab, report_tab, summary_tab, chat_tab, history_tab, admin_tab, logout_btn, tabs, compare_reports]
		)

		# 보고서 목록 표에서 줄을 누르면 그 보고서를 선택
		report_list_components["table"].select(
			fn=on_report_select,
			inputs=[report_list_components["listed_ids"], state],
			outputs=[state, report_list_components["message"]]
		)

		# 요약 보기 버튼 누르면 요약 탭으로
		go_summary_btn.click(
			fn=on_view_summary,
			inputs=state,
			outputs=[tabs, summary_components["report_dropdown"]]
		)

		# 내 기록 탭을 열면 기록 표·대화 선택 목록 채우기
		history_tab.select(
			fn=on_load_history,
			inputs=state,
			outputs=[history_components["table"], history_components["session_dropdown"]]
		)
		
		# 대화 이어가기 버튼 누르면 질의응답 탭 Chatbot에 이전 대화 채우기
		history_components["restore_btn"].click(
			fn=on_restore,
			inputs=[history_components["session_dropdown"], state],
			outputs=[chat_components["chatbot"], state]
		)		

		# 질의응답으로 이동 버튼 누르면 질의응답 탭으로
		go_chat_btn.click(
			fn=on_go_chat,
			inputs=state,
			outputs=[tabs, chat_components["report_dropdown"]]
		)

		# 지표 추출·비교 버튼 누르면 비교표, 차트 보여주기
		compare_btn.click(
			fn=on_compare,
			inputs=compare_reports,
			outputs=[compare_table, compare_chart]
		)

		# 업로드 버튼 누르면 진행 상황·결과를 보여주고, 요약·질의응답 탭 보고서 드롭다운 갱신
		upload_components["upload_btn"].click(
			fn=on_upload,
			inputs=[upload_components["file"], state],
			outputs=[upload_components["result"], summary_components["report_dropdown"], chat_components["report_dropdown"]]
		)

		# 요약·분석 탭을 열면 보고서 드롭다운 채우기 (질의응답 탭과 같은 refresh_report_choices 사용)
		summary_components["tab"].select(
			fn=refresh_report_choices,
			inputs=[state, summary_components["report_dropdown"]],
			outputs=summary_components["report_dropdown"]
		)

		# 요약하기 버튼 누르면 선택한 보고서 요약 보여주기
		summary_components["summarize_btn"].click(
			fn=on_summarize,
			inputs=summary_components["report_dropdown"],
			outputs=summary_components["summary_result"]
		)

		# 요청 실행 버튼 누르면 자연어 요청 결과 보여주기
		summary_components["request_btn"].click(
			fn=on_request,
			inputs=[summary_components["request"], summary_components["report_dropdown"]],
			outputs=summary_components["request_result"]
		)

	return demo


def main():
	"""
	앱 실행하기

	순서
	1. load_settings()로 .env 설정을 읽는다
	2. 그래프 4개(업로드·질의응답·요약·에이전트)를 미리 한 번씩 만들어 둔다 (예열)
	   → 처음 쓰는 사람이 기다리지 않게 하려고
	3. build_app()으로 화면을 만들고 http://localhost:7860 에서 실행한다

	입력: 없음
	출력: 없음
	"""
	# 설정 읽기
	load_settings()

	# 그래프 미리 만들기
	get_ingest_graph()
	get_qa_graph()
	get_summary_graph()
	get_agent_graph()

	# 화면 띄우기
	demo = build_app()
	demo.launch(server_port=7860, theme=gr.themes.Soft())