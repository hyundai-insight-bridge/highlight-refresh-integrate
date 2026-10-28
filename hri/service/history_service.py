"""질문 기록·세션 유지 · save_qa_log, get_history, restore_session (임세준)

질의응답이 끝나면 save_log_node()가 save_qa_log()를 불러 기록을 남긴다.
저장하기 전에 질문·답변의 개인정보(전화번호·이메일)를 가리고, 저장은 insert_qa_log()가 한다.
(같은 파일의 get_history()·restore_session()은 3.6.7에서 추가)
"""
from hri.dao.qa_log_dao import insert_qa_log
from hri.domain.schemas import QALog


def save_qa_log(log: QALog) -> int:
	"""
	질문 기록 저장하기 (개인정보 가린 뒤)

	순서
	1. mask_pii()로 질문과 답변 속 전화번호·이메일을 가린다
	   예) 010-1234-5678 → 010-****-5678, kim@naver.com → ki***@naver.com
	2. 가린 질문·답변으로 새 QALog를 만든다
	   (받은 log는 그대로 두고 새로 만들어서, 부른 쪽의 값이 바뀌지 않게 함)
	3. insert_qa_log()로 qa_logs에 저장하고 log_id를 돌려준다

	- 저장하는 값: 질문·답변·페르소나·route('rag'|'no_answer'|'chat'|'error')·근거 유무·
	  응답 시간·토큰 수·원화 비용·오류 내용 (+ user_id·session_id)
	- 돌려준 log_id는 save_log_node()가 insert_usage(flow='qa', ref_id=log_id)에 쓴다
	- qa_service가 그래프(save_log_node)를 거쳐 이 파일을 다시 불러오면
	  서로가 서로를 부르는 순환 import가 될 수 있어서, 맨 위가 아니라 함수 안에서 불러온다

	입력: log (QALog, log_id·created_at은 None)
	출력: int (저장된 기록 번호 log_id)
	"""
	from hri.service.qa_service import mask_pii

	# 1) 질문·답변의 개인정보 가리기
	masked_question = mask_pii(log.question)
	masked_answer = mask_pii(log.answer)

	# 2) 가린 값으로 새 QALog 만들기 (나머지 값은 그대로)
	masked_log = QALog(
		user_id=log.user_id,
		session_id=log.session_id,
		question=masked_question,
		answer=masked_answer,
		persona=log.persona,
		route=log.route,
		has_source=log.has_source,
		response_ms=log.response_ms,
		tokens=log.tokens,
		cost_krw=log.cost_krw,
		error=log.error
	)

	# 3) 저장하고 log_id 돌려주기
	log_id = insert_qa_log(masked_log)

	return log_id