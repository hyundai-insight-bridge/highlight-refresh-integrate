"""내 기록 화면 · build_history_tab, on_restore (임세준)

로그인한 사용자가 지난 질문 기록을 대화(session)별로 보고,
고른 대화를 질의응답 탭에서 이어서 질문할 수 있게 하는 화면.
- build_history_tab(): 기록 표(gr.Markdown)·대화 선택(gr.Dropdown)·'대화 이어가기' 버튼 배치
- on_restore(): 고른 대화를 질의응답 탭 Chatbot에 채우고 state의 session_id를 바꾼다
- 버튼 연결은 state·질의응답 탭 Chatbot이 필요해서 app.py의 build_app()에서 한다
- 그래서 build_app()에서 쓸 화면 부품을 history_components에 담아 둔다
"""
import gradio as gr

from hri.loader.table_loader import table_to_markdown
from hri.service.history_service import restore_session
from hri.util.logger import safe_call


# build_app()에서 버튼을 연결할 때 쓰려고 화면 부품을 저장해 둠
history_components = {}


def build_history_tab():
	"""
	내 기록 화면 만들기

	세션별 질문 기록을 table_to_markdown()으로 그린 gr.Markdown과
	세션 선택 gr.Dropdown·'대화 이어가기' gr.Button을 배치한다.

	- 기록 표는 [마지막 시각, 첫 질문, 질문 수] 머리글로 그린다
	- 탭은 로그인 전에는 숨겨 둔다 (visible=False, 로그인하면 on_login이 보이게 함)
	- '대화 이어가기' 버튼 연결은 build_app()에서 하므로 부품을 history_components에 담아 둔다

	입력: 없음
	출력: gr.Tab (내 기록 탭)
	"""
	# 세션별 질문 기록 표 머리글
	rows = [["마지막 시각", "첫 질문", "질문 수"]]

	with gr.Tab("내 기록", id="history", visible=False) as history_tab:
		# 세션별 질문 기록 표
		history_table = gr.Markdown(table_to_markdown(rows))

		# 이어갈 대화 고르기
		with gr.Row():
			session_dropdown = gr.Dropdown(label="대화 선택", choices=[], scale=4)
			restore_btn = gr.Button("대화 이어가기", variant="primary", scale=1)

	# build_app()에서 쓸 부품 저장
	history_components["table"] = history_table
	history_components["session_dropdown"] = session_dropdown
	history_components["restore_btn"] = restore_btn

	return history_tab


@safe_call
def on_restore(session_id: str, state):
	"""
	대화 이어가기 버튼 눌렀을 때

	선택한 session_id로 restore_session()을 호출해 질의응답 탭의 gr.Chatbot에 이전 대화를 채우고,
	state['session_id']를 선택한 세션으로 바꿔 다음 질문이 같은 thread로 이어지게 한다.

	순서
	1. restore_session(session_id, user_id)로 이전 대화를 Chatbot 형식으로 받는다
	   (질의응답 그래프의 대화 기억도 이때 되살아남)
	2. state['session_id']를 고른 대화로 바꾼다
	3. (Chatbot에 넣을 대화, 바뀐 state)를 돌려준다

	- restore_session()은 user_id도 받는다 (3.6.7, 다른 사람의 대화를 불러오지 못하게)

	입력: session_id (드롭다운에서 고른 대화 번호), state (gr.State)
	출력: tuple (list[dict] Chatbot 대화, gr.State)
	"""
	# 1) 이전 대화 불러오기
	user_id = state["user"]["user_id"]
	chat_history = restore_session(session_id, user_id)

	# 2) 다음 질문이 같은 대화로 이어지게 session_id 바꾸기
	state["session_id"] = session_id

	# 3) Chatbot 대화와 state 돌려주기
	return chat_history, state