"""보고서 탭 · build_upload_tab, on_upload (김희진) / build_report_list_panel (장유빈)"""
import gradio as gr

from hri.service.report_service import search_reports
from hri.service.document_service import upload_report
# ---------------------------------------------------------------------
# [장유빈] 보고서 목록·검색 화면 
# ---------------------------------------------------------------------
TABLE_HEADERS = ["제목", "발행기관", "발행일", "청크 수"]
NO_PUBLISHER = "확인할 수 없는 발행기관"
NO_RESULT_MESSAGE = "검색 결과가 없습니다"
NEED_SELECT_MESSAGE = "보고서를 선택하세요"
SUMMARY_TAB_ID = "summary"  # app.py의 요약·분석 탭 id (build_summary_tab과 맞출 것)
CHAT_TAB_ID = "chat"  # app.py의 질의응답 탭 id (build_chat_tab과 맞출 것)

# app.py가 표 선택(select)을 연결할 때 쓰는 컴포넌트 모음 (login_components 등과 같은 방식)
report_list_components = {}


def build_report_list_panel():
	"""보고서 목록·검색 화면을 만든다. (gr.Blocks 안에서 호출)

	검색어 입력칸·검색 버튼과, 눌러서 펼치는 '보고서 목록' 메뉴(보고서 표)를 둔다.
	메뉴를 펼치거나 검색하면 목록을 불러오고, 표에서 한 줄을 누르면 그 보고서를 선택한다.
	선택한 보고서의 report_id는 state['report_ids']에 담겨 요약·질의응답 탭으로 넘어간다.

	반환: (화면 Column, '요약 보기' 버튼, '질의응답으로 이동' 버튼)
	표 선택(table.select)과 이동 버튼의 click 연결은 app.py의 build_app()에서 한다
	(표·report_id 목록·안내 문구는 report_list_components로 꺼내 쓴다).
	"""
	with gr.Column() as panel:
		with gr.Row():
			keyword = gr.Textbox(
				label="검색어",
				placeholder="제목 또는 발행기관 (비워 두고 검색하면 전체 목록)",
				scale=4,
			)
			search_btn = gr.Button("검색", variant="primary", scale=1)

		# 눌러서 펼치는 보고서 목록 (처음에는 접혀 있음)
		with gr.Accordion("보고서 목록 (눌러서 펼치기)", open=False) as list_menu:
			table = gr.Dataframe(
				headers=TABLE_HEADERS,
				datatype=["str", "str", "str", "number"],
				value=[],
				interactive=False,
				wrap=True,
			)
			message = gr.Markdown()

		with gr.Row():
			go_summary_btn = gr.Button("요약 보기")
			go_chat_btn = gr.Button("질의응답으로 이동")

		# 표의 각 줄이 어떤 report_id인지 기억해 두는 값 (표에는 report_id 열이 없다)
		listed_ids = gr.State([])

	outputs = [table, listed_ids, message]
	# 메뉴를 펼칠 때 목록을 불러온다 (검색어가 비어 있으면 전체 목록)
	list_menu.expand(on_report_search, inputs=keyword, outputs=outputs)
	# 검색하면 결과를 채우고, 접혀 있으면 메뉴를 펼쳐서 보여 준다
	search_btn.click(on_report_search, inputs=keyword, outputs=outputs).then(
		lambda: gr.update(open=True), outputs=list_menu
	)
	keyword.submit(on_report_search, inputs=keyword, outputs=outputs).then(
		lambda: gr.update(open=True), outputs=list_menu
	)
	report_list_components.update(table=table, listed_ids=listed_ids, message=message)
	return panel, go_summary_btn, go_chat_btn


def on_report_search(keyword: str):
	"""검색어로 보고서를 찾아 표에 넣을 값을 만든다.

	반환: (표 행 목록, 각 행의 report_id 목록, 안내 문구)
	결과가 없으면 빈 표와 '검색 결과가 없습니다'를 돌려준다.
	"""
	reports = search_reports(keyword or "")
	if not reports:
		return [], [], NO_RESULT_MESSAGE
	rows = [
		[
			r.title,
			r.publisher or NO_PUBLISHER,
			r.published_date.isoformat() if r.published_date else "",
			r.chunk_count,
		]
		for r in reports
	]
	ids = [r.report_id for r in reports]
	return rows, ids, f"총 {len(rows)}건"


def on_report_select(evt: gr.SelectData, report_ids: list[int], state: dict):
	"""표에서 누른 줄의 보고서를 선택해 state['report_ids']에 담는다.

	반환: (바뀐 state, 안내 문구)
	"""
	row = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
	if not report_ids or row >= len(report_ids):
		return state, NEED_SELECT_MESSAGE
	new_state = {**state, "report_ids": [report_ids[row]]}
	title = evt.row_value[0] if evt.row_value else ""
	return new_state, f"선택한 보고서: {title}"


def _go_selected(state: dict, tab_id: str):
	"""선택한 보고서가 있으면 tab_id 탭으로 옮기고 그 보고서를 드롭다운 값으로 돌려준다.

	선택한 보고서가 없으면 경고만 띄우고 화면은 그대로 둔다.
	"""
	report_ids = (state or {}).get("report_ids") or []
	if not report_ids:
		gr.Warning(NEED_SELECT_MESSAGE)
		return gr.update(), gr.update()
	return gr.update(selected=tab_id), gr.update(value=report_ids[0])


def on_view_summary(state: dict):
	"""'요약 보기' 버튼: 요약·분석 탭으로 옮기고 선택한 보고서를 고른다.

	반환: (Tabs 갱신, 요약 탭 보고서 드롭다운 갱신)
	"""
	return _go_selected(state, SUMMARY_TAB_ID)


def on_go_chat(state: dict):
	"""'질의응답으로 이동' 버튼: 질의응답 탭으로 옮기고 선택한 보고서를 고른다.

	반환: (Tabs 갱신, 질의응답 탭 보고서 드롭다운 갱신)
	"""
	return _go_selected(state, CHAT_TAB_ID)

# ----------------------------------------
# [김희진] 업로드 화면
# ----------------------------------------
# 업로드 그래프 노드 이름 -> 화면에 보여 줄 단계 이름 (upload_report가 내보내는 step 값)
STEP_LABELS = {
	"validate": "PDF 검증",
	"load_text": "텍스트 추출",
	"extract_tables": "표 추출",
	"extract_charts": "차트 감지",
	"process_charts": "차트 분석(OCR)",
	"split": "청크 분할",
	"summarize_tables": "표, 차트 요약",
	"persist": "저장"
}
NEED_FILE_MESSAGE = "PDF 파일을 선택하세요."
NEED_LOGIN_MESSAGE = "로그인이 필요합니다."

# app.py가 업로드 버튼 click을 연결할 때 쓰는 컴포넌트 모음 (login_components 등과 같은 방식)
upload_components = {}

def build_upload_tab():
	"""보고서 업로드 화면을 만든다. (gr.Tabs 안에서 호출)
	PDF 선택칸(file_types=['.pdf']), 업로드 버튼, 처리 결과 Markdown을 둔다.
	업로드 버튼 click은 요약, 질의응답 탭의 드롭다운도 갱신해야 해서 build_app()에서 on_upload()에 연결한다.
	(파일, 버튼, 결과는 upload_components로 꺼내 쓴다).
	
	출력: gr.Tab (업로드 탭)
	"""
	with gr.Tab("업로드", id="upload") as tab:
		file = gr.File(label="보고서 PDF", file_types=[".pdf"], type="filepath")
		upload_btn = gr.Button("업로드", variant="primary")
		result = gr.Markdown()

		upload_components.update(file=file, upload_btn=upload_btn, result=result)
		return tab

def _progress_markdown(done_steps: list[str]) -> str:
	"""끝난 단계를 체크 표시로 보여 주는 진행 상황 문구."""
	lines = [f"✅ {STEP_LABELS.get(step, step)}" for step in done_steps]
	return "### 처리 증 ...\n" + "\n".join(lines)

def _result_markdown(event:dict, report) -> str:
	"""업로드 성공 결과 문구 (보고서 정보 + 청크 수 + 차트 경고)."""
	counts = event.get("counts") or {}
	warnings = event.get("warnings") or []
	lines = ["### ✅ 업로드 완료"]

	if report:
		lines += [
			f"- **보고서명**: {report.title}",
			f"- **발행기관**: {report.publisher or NO_PUBLISHER}",
			f"- **발행일**: {report.published_date.isformat() if report.published_date else '확인할 수 없음'}",
			f"- **페이지 수**: {report.page_count}"
		]
	lines.append(
		f"- **청크 수**: 텍스트 {counts.get('text', 0)}, 표 {counts.get('table', 0)}, 차트 {counts.get('chart', 0)}"
	)
	if warnings:
		lines.append(f"\n⚠️ **확인이 필요한 항목 {len(warnings)}건**")
		lines += [f"- {w}" for w in warnings]

	return "\n".join(lines)

def on_upload(file_path: str | None, state: dict):
	"""업로드 버튼: upload_report()가 내보내는 진행 상황을 Markdown에 차례로 갱신한다. (제네레이터)
	
	순서
	1. 파일이 없거나 로그인 전이면 안내만 보여 준다
	2. progress 이벤트마다 끝난 단계 목록을 갱신해 보여 준다
	3. error 이벤트(검증 실패 등)면 사유를 보여 주고 끝낸다
	4. result 이벤트면 보고서 정보, 청크 수, 차트 경고를 보여 주고, search_reports()로 요약, 질의응답 탭의 보고서 드롭다운 choices를 갱신한다
	
	yield 값: (진행/결과 Markdown, 요약 탭 드롭다운 갱신, 질의응답 탭 드롭다운 갱신)
	"""
	keep = gr.update() # "바꾸지 않음"

	# 1. 입력 확인
	if not file_path:
		yield NEED_FILE_MESSAGE, keep, keep
		return
	user = (state or {}).get("user")

	if not user:
		yield NEED_LOGIN_MESSAGE, keep, keep
		return

	# 2. 단계별 진행
	done_steps: list[str] = []
	yield "### 처리 중...\n⏳ 시작합니다", keep, keep

	for event in upload_report(file_path, user["user_id"]):
		kind = event.get("type")

		if kind == "progress":
			done_steps.append(event["step"])
			yield _progress_markdown(done_steps), keep, keep
		elif kind == "error":
			# 3. 검증 실패 사유 등
			yield f"### ❌ 업로드 실패\n{event.get('reason', '알 수 없는 오류')}", keep, keep
			return
		elif kind == "result":
			# 4. 완료: 드롭다운 갱신용 목록 (못 가져와도 결과는 보여 준다)
			report = None
			choices = None
			try:
				reports = search_reports()
				choices = [(r.title, r.report_id) for r in reports]
				report = next((r for r in reports if r.report_id == event.get("report_id")), None)
			except Exception:
				pass

			dropdown = gr.update(choices=choices) if choices is not None else keep
			yield _result_markdown(event, report), dropdown, dropdown