"""질의응답 탭 · build_chat_tab, respond_stream (장유빈) / on_suggest_click, on_term_click (류현수) / on_feedback (임세준)"""
import logging

import gradio as gr

from hri.domain.schemas import AnswerResult
from hri.service.report_service import search_reports

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# [장유빈] 질의응답 화면 · build_chat_tab, respond_stream
# ---------------------------------------------------------------------
CHAT_TAB_ID = "chat"  # app.py의 질의응답 탭 id (report_view.CHAT_TAB_ID와 같아야 한다)
PERSONA_CHOICES = ["입문자", "실무자", "전문가"]
DEFAULT_PERSONA = "실무자"
DEFAULT_K = 4
MAX_SUGGESTIONS = 3  # 추천 질문 버튼 개수
NEED_LOGIN_MESSAGE = "로그인 후 이용해 주세요."
ERROR_MESSAGE = "답변을 만드는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

# app.py·다른 담당자가 컴포넌트를 꺼내 쓸 때 쓰는 모음 (login_components 등과 같은 방식)
chat_components = {}


def _ask_stream(**kwargs):
	"""qa_service.ask_stream을 호출하는 시점에 불러와 실행한다.

	qa_service는 그래프(.env 설정 필요)를 불러오는 모듈이라, 화면 파일을 불러올 때가 아니라
	실제로 질문할 때 가져온다 (화면 테스트가 .env 없이도 돌아가고, 테스트에서 이 함수만 바꿔 끼울 수 있다).
	"""
	from hri.service.qa_service import ask_stream

	return ask_stream(**kwargs)


def _user_id(state: dict) -> str | None:
	"""state['user']에서 로그인한 사용자의 아이디를 꺼낸다. 로그인 전이면 None.

	user가 dict여도, user_id 속성을 가진 객체(User)여도 읽을 수 있다.
	"""
	user = (state or {}).get("user")
	if user is None:
		return None
	if isinstance(user, dict):
		return user.get("user_id")
	return getattr(user, "user_id", None)


def _sources_to_markdown(sources: list[dict]) -> str:
	"""format_sources() 결과를 화면에 보여 줄 Markdown으로 바꾼다.

	한 줄에 '보고서명 · p.쪽수 · 섹션명(차트는 그림 n(차트))'이다. 섹션명이 없는 표는 '표'로 적는다.
	출처가 없으면 빈 문자열을 돌려준다 ('자료에 없습니다' 답변에는 출처를 보이지 않는다).
	"""
	if not sources:
		return ""
	lines = ["**출처**"]
	for source in sources:
		start, end = source["page_start"], source["page_end"]
		pages = f"p.{start}" if start == end else f"p.{start}-{end}"
		label = source["label"] or ("표" if source["kind"] == "table" else "")
		lines.append("- " + " · ".join(part for part in (source["report_title"], pages, label) if part))
	return "\n".join(lines)


def _suggest_updates(suggestions: list[str]) -> list:
	"""추천 질문 버튼 MAX_SUGGESTIONS개의 갱신값을 만든다. 질문이 있는 버튼만 보이고 나머지는 숨긴다."""
	updates = []
	for i in range(MAX_SUGGESTIONS):
		if i < len(suggestions):
			updates.append(gr.update(value=suggestions[i], visible=True))
		else:
			updates.append(gr.update(value="", visible=False))
	return updates


def build_chat_tab():
	"""질의응답 탭 화면을 만든다. (gr.Blocks의 gr.Tabs 안에서 호출)

	화면을 반으로 나눈다.
	- 왼쪽 반(챗봇): 맨 위에 페르소나(입문자/실무자/전문가)·보고서 선택(여러 개 가능)·검색 옵션(k, MMR),
	  그 아래에 대화창(gr.Chatbot)·질문 입력칸·전송 버튼·출처·추천 질문 버튼 3개.
	- 오른쪽 반(용어 검색): 눌러서 접고 펼치는 '용어 검색' 메뉴(gr.Accordion). 안의 검색 창은
	  build_term_panel(류현수)이 들어오면 이 메뉴 안에서 부른다.
	추천 질문·👍/👎 버튼은 숨겨 두고, 답변이 끝난 뒤 respond_stream()이 추천 질문 버튼을 보여 준다.
	피드백 버튼은 on_feedback(임세준)이 연결될 때 보이게 한다.
	탭은 로그인 전에는 숨겨 둔 채(visible=False) 만들고, 로그인하면 on_login이 보이게 한다.
	이벤트 연결은 gr.State가 필요해서 build_app()이 connect_chat_events(state)로 한다.

	반환: gr.Tab (컴포넌트는 chat_components로 꺼내 쓴다)
	"""
	with gr.Tab("질의응답", id=CHAT_TAB_ID, visible=False) as tab:
		with gr.Row():
			# 왼쪽 반: 챗봇
			with gr.Column(scale=1):
				with gr.Row():
					persona = gr.Radio(PERSONA_CHOICES, value=DEFAULT_PERSONA, label="페르소나", scale=2)
					report_dropdown = gr.Dropdown(label="보고서 선택 (여러 개 가능)", choices=[], multiselect=True, scale=3)
				with gr.Accordion("검색 옵션", open=False):
					k = gr.Slider(1, 10, value=DEFAULT_K, step=1, label="가져올 근거 수 (k)")
					use_mmr = gr.Checkbox(label="MMR 사용 (서로 다른 근거 고르기)", value=False)
				chatbot = gr.Chatbot(label="질의응답", height=480)
				with gr.Row():
					message = gr.Textbox(
						label="질문",
						placeholder="선택한 보고서에 대해 궁금한 점을 물어보세요",
						lines=1,
						scale=5,
					)
					send_btn = gr.Button("전송", variant="primary", scale=1)
				sources = gr.Markdown()
				# 추천 질문: 처음에는 숨기고 답변이 끝나면 질문이 있는 만큼 보여 준다
				suggest_buttons = [gr.Button(value="", visible=False) for _ in range(MAX_SUGGESTIONS)]
				# 피드백: on_feedback(임세준)이 연결될 때 보이게 한다 (2차)
				with gr.Row():
					like_btn = gr.Button("👍", visible=False, scale=0)
					dislike_btn = gr.Button("👎", visible=False, scale=0)
			# 오른쪽 반: 용어 검색 (접고 펼치는 메뉴)
			with gr.Column(scale=1):
				with gr.Accordion("용어 검색", open=False) as term_menu:
					# build_term_panel(류현수)이 들어오면 이 안에서 부르고, 아래 안내 문구는 지운다
					gr.Markdown("용어 검색 기능을 준비 중입니다.")

	chat_components.update(
		tab=tab,
		chatbot=chatbot,
		message=message,
		send_btn=send_btn,
		sources=sources,
		suggest_buttons=suggest_buttons,
		like_btn=like_btn,
		dislike_btn=dislike_btn,
		persona=persona,
		report_dropdown=report_dropdown,
		k=k,
		use_mmr=use_mmr,
		term_menu=term_menu,
	)
	return tab


def refresh_report_choices(state: dict, selected: list[int] | None):
	"""보고서 드롭다운의 선택지를 DB의 보고서 목록으로 채운다. (질의응답 탭을 열 때 실행)

	선택지는 (제목, report_id) 쌍이다. 이미 고른 보고서가 있으면 그대로 두고,
	없으면 보고서 목록 화면에서 고른 state['report_ids']를 고른 상태로 둔다. 목록에 없는 번호는 뺀다.
	"""
	reports = search_reports("")
	choices = [(r.title, r.report_id) for r in reports]
	existing = {r.report_id for r in reports}
	wanted = selected or (state or {}).get("report_ids") or []
	return gr.update(choices=choices, value=[i for i in wanted if i in existing])


def respond_stream(message: str, history: list, persona: str, report_ids: list[int], k: int, use_mmr: bool, state: dict):
	"""질문을 ask_stream()에 보내고, 글자 조각이 올 때마다 대화창을 갱신하며 답변이 흘러나오게 한다.

	처음에 입력칸을 비우고 이전 출처·추천 질문을 지운다. 글자 조각(str)은 마지막 답변에 이어 붙이고,
	마지막에 AnswerResult가 오면 출처(Markdown)·추천 질문 버튼·state['last_log_id']를 갱신한다.
	로그인 전이면 안내만 하고, 질문 처리 중 예외가 나면 오류 안내 문구를 답변으로 보여 준다.

	반환(yield): (대화 기록, 질문 입력칸, 출처, 추천 질문 버튼 3개, state) — build_chat_tab 컴포넌트 순서와 같다.
	"""
	state = state or {}
	history = list(history or [])
	history.append({"role": "user", "content": message})
	history.append({"role": "assistant", "content": ""})
	keep = gr.update()  # 값을 바꾸지 않는 갱신

	user_id = _user_id(state)
	if user_id is None:
		history[-1]["content"] = NEED_LOGIN_MESSAGE
		yield history, keep, keep, *[keep] * MAX_SUGGESTIONS, state
		return

	# 새 질문이 시작되면 입력칸을 비우고 이전 질문의 출처·추천 질문을 지운다
	yield history, "", "", *_suggest_updates([]), state

	answer = ""
	try:
		stream = _ask_stream(
			question=message,
			persona=persona,
			session_id=state.get("session_id"),
			user_id=user_id,
			report_ids=list(report_ids) if report_ids else None,
			k=int(k),
			use_mmr=bool(use_mmr),
		)
		for chunk in stream:
			if isinstance(chunk, AnswerResult):
				# 마지막 결과: 최종 답변·출처·추천 질문·기록 번호(피드백용)를 반영한다
				history[-1]["content"] = chunk.answer or answer
				new_state = {**state, "last_log_id": chunk.log_id}
				yield history, keep, _sources_to_markdown(chunk.sources), *_suggest_updates(chunk.suggestions), new_state
				return
			answer += chunk
			history[-1]["content"] = answer
			yield history, keep, keep, *[keep] * MAX_SUGGESTIONS, state
	except Exception:
		logger.exception("질의응답 처리 중 오류")
		history[-1]["content"] = ERROR_MESSAGE
		yield history, keep, keep, *[keep] * MAX_SUGGESTIONS, state


def connect_chat_events(state: gr.State) -> None:
	"""질의응답 탭의 이벤트를 연결한다. (build_app()의 gr.Blocks 안에서 build_chat_tab() 뒤에 호출)

	- 질문 입력칸에서 Enter, 전송 버튼 클릭 → respond_stream (답변이 흘러나옴)
	- 질의응답 탭을 열 때 → refresh_report_choices (보고서 선택지 채우기)
	"""
	c = chat_components
	stream_inputs = [c["message"], c["chatbot"], c["persona"], c["report_dropdown"], c["k"], c["use_mmr"], state]
	stream_outputs = [c["chatbot"], c["message"], c["sources"], *c["suggest_buttons"], state]
	c["message"].submit(respond_stream, inputs=stream_inputs, outputs=stream_outputs)
	c["send_btn"].click(respond_stream, inputs=stream_inputs, outputs=stream_outputs)
	c["tab"].select(refresh_report_choices, inputs=[state, c["report_dropdown"]], outputs=c["report_dropdown"])
