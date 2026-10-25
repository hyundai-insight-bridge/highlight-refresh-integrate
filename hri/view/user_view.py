"""로그인 화면 · build_login_tab, on_login, on_register, on_logout (임세준)"""

import uuid
import gradio as gr

from hri.service.user_service import login, register
from hri.exception.errors import LoginFailedError, DuplicateUserError


# build_app에서 로그인 버튼 연결할 때 쓰려고 저장해둠
login_components = {}


def build_login_tab():
	"""로그인 화면 만들기"""
	with gr.Tab("로그인", id="login") as login_tab:
		title = gr.Markdown("## 로그인")

		user_id = gr.Textbox(label="아이디", placeholder="아이디를 입력하세요")
		password = gr.Textbox(label="비밀번호", type="password", placeholder="비밀번호를 입력하세요")
		# 이름은 회원가입할 때만 보여줌
		name = gr.Textbox(label="이름", placeholder="이름을 입력하세요", visible=False)

		# 로그인 화면 버튼
		with gr.Row():
			login_btn = gr.Button("로그인", variant="primary")
			go_register_btn = gr.Button("회원가입")

		# 회원가입 화면 버튼 (처음에는 숨김)
		with gr.Row():
			register_btn = gr.Button("가입하기", variant="primary", visible=False)
			go_login_btn = gr.Button("로그인 화면으로", visible=False)

		message = gr.Markdown()

		# 회원가입 화면으로 바꾸는 함수
		def show_register_form():
			"""회원가입 화면으로 바꾸기"""
			return (
				gr.update(label="회원가입"),  # 탭 이름
				"## 회원가입",  # 제목
				gr.update(visible=True),  # 이름 입력칸
				gr.update(visible=False),  # 로그인 버튼
				gr.update(visible=False),  # 회원가입 버튼
				gr.update(visible=True),  # 가입하기 버튼
				gr.update(visible=True),  # 로그인 화면으로 버튼
				""  # 메시지 지우기
			)

		# 로그인 화면으로 바꾸는 함수
		def show_login_form():
			"""로그인 화면으로 바꾸기"""
			return (
				gr.update(label="로그인"),  # 탭 이름
				"## 로그인",  # 제목
				gr.update(visible=False),  # 이름 입력칸
				gr.update(visible=True),  # 로그인 버튼
				gr.update(visible=True),  # 회원가입 버튼
				gr.update(visible=False),  # 가입하기 버튼
				gr.update(visible=False),  # 로그인 화면으로 버튼
				""  # 메시지 지우기
			)

		# 회원가입 버튼 누르면 회원가입 화면으로
		go_register_btn.click(
			show_register_form,
			outputs=[login_tab, title, name, login_btn, go_register_btn, register_btn, go_login_btn, message]
		)

		# 로그인 화면으로 버튼 누르면 로그인 화면으로
		go_login_btn.click(
			show_login_form,
			outputs=[login_tab, title, name, login_btn, go_register_btn, register_btn, go_login_btn, message]
		)

		# 가입하기 버튼 누르면 회원가입
		register_btn.click(on_register, inputs=[user_id, password, name], outputs=message)

	login_components["user_id"] = user_id
	login_components["password"] = password
	login_components["login_btn"] = login_btn
	login_components["message"] = message

	return login_tab


def on_login(user_id: str, password: str):
	"""로그인 버튼 눌렀을 때"""
	# 빈칸이면 화면은 그대로 두고 메시지만 보여줌
	if not user_id or not password:
		return (
			gr.update(),  # state
			gr.update(),  # 로그인 탭
			gr.update(),  # 보고서 탭
			gr.update(),  # 요약 탭
			gr.update(),  # 질의응답 탭
			gr.update(),  # 내 기록 탭
			gr.update(),  # 관리자 탭
			"아이디와 비밀번호를 입력하세요."
		)

	try:
		user = login(user_id, password)
	except LoginFailedError:
		# 로그인 실패하면 화면은 그대로 두고 메시지만 보여줌
		return (
			gr.update(),  # state
			gr.update(),  # 로그인 탭
			gr.update(),  # 보고서 탭
			gr.update(),  # 요약 탭
			gr.update(),  # 질의응답 탭
			gr.update(),  # 내 기록 탭
			gr.update(),  # 관리자 탭
			"아이디 또는 비밀번호가 올바르지 않습니다."
		)

	# 로그인한 사람 정보
	user_info = {
		"user_id": user.user_id,
		"name": user.name,
		"role": user.role,
		"created_at": user.created_at
	}

	# state에 저장할 값
	state = {
		"user": user_info,
		"session_id": str(uuid.uuid4()),
		"report_ids": [],
		"last_log_id": None
	}

	# 관리자면 관리자 탭도 보여줌
	if user.role == "admin":
		show_admin = True
	else:
		show_admin = False

	# 로그인 탭은 숨기고 나머지 탭은 보여줌
	return (
		state,
		gr.update(visible=False),  # 로그인 탭
		gr.update(visible=True),  # 보고서 탭
		gr.update(visible=True),  # 요약 탭
		gr.update(visible=True),  # 질의응답 탭
		gr.update(visible=True),  # 내 기록 탭
		gr.update(visible=show_admin),  # 관리자 탭
		""  # 메시지 지우기
	)


def on_register(user_id: str, password: str, name: str):
	"""가입하기 버튼 눌렀을 때"""
	if not user_id or not password or not name:
		return "아이디, 비밀번호, 이름을 모두 입력하세요."

	try:
		result = register(user_id, password, name)
	except DuplicateUserError:
		return "이미 사용 중인 아이디입니다."

	if result == True:
		return "회원가입이 완료되었습니다. 로그인해 주세요."
	else:
		return "회원가입에 실패했습니다. 다시 시도해주세요."


def on_logout(state):
	"""로그아웃 버튼 눌렀을 때"""
	# 사용자 정보 지우고 session_id 새로 만들기
	state["user"] = None
	state["session_id"] = str(uuid.uuid4())

	# 로그인 탭만 보여줌
	return (
		state,
		gr.update(visible=True),  # 로그인 탭
		gr.update(visible=False),  # 보고서 탭
		gr.update(visible=False),  # 요약 탭
		gr.update(visible=False),  # 질의응답 탭
		gr.update(visible=False),  # 내 기록 탭
		gr.update(visible=False)  # 관리자 탭
	)