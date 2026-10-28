"""질문 기록 · insert_qa_log, select_logs, update_feedback (임세준)

질의응답 한 번의 기록(질문·답변·응답 시간·토큰·비용 등)을 qa_logs 테이블에 저장하는 DAO.
save_qa_log()(history_service)가 개인정보를 가린 뒤 이 함수를 부른다.
(같은 파일의 select_logs()는 3.6.7 기록 조회에서 추가)
"""
from hri.dao.db import get_connection
from hri.domain.schemas import QALog


def insert_qa_log(log: QALog) -> int:
	"""
	질문 기록 한 줄 저장하기

	QALog에 담긴 값을 qa_logs 테이블에 INSERT 한다.
	- log_id(번호)와 created_at(저장 시간)은 DB가 알아서 만든다
	- feedback은 저장할 때는 비어 있고(NULL), 👍/👎를 누르면 update_feedback()이 채운다

	순서
	1. sql: 저장할 SQL을 만든다 (값 자리는 %s로 비워 둠)
	2. values: %s 자리에 순서대로 들어갈 값을 튜플로 만든다
	3. get_connection()으로 DB에 연결해서 실행하고 commit으로 저장한다
	4. cursor.lastrowid로 방금 저장한 줄의 번호(log_id)를 받아서 돌려준다

	입력: log (QALog)
	출력: int (방금 저장한 기록 번호 log_id)
	"""
	sql = """
		INSERT INTO qa_logs (
			user_id, session_id, question, answer, persona, route,
			has_source, response_ms, tokens, cost_krw, error
		)
		VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
	"""

	values = (
		log.user_id,
		log.session_id,
		log.question,
		log.answer,
		log.persona,
		log.route,
		log.has_source,
		log.response_ms,
		log.tokens,
		log.cost_krw,
		log.error
	)

	with get_connection() as conn:
		cursor = conn.cursor()
		cursor.execute(sql, values)
		conn.commit()
		log_id = cursor.lastrowid

	return log_id