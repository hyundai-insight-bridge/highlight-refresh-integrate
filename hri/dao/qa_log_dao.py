"""질문 기록 · insert_qa_log, select_logs, update_feedback (임세준)

질의응답 한 번의 기록(질문·답변·응답 시간·토큰·비용 등)을 qa_logs 테이블에 저장하고 조회하는 DAO.
- insert_qa_log(): 기록 저장 (save_qa_log()가 개인정보를 가린 뒤 부름)
- select_logs(): 기록 조회 (내 기록 화면·세션 복원에서 부름)
- update_feedback(): 답변별 👍/👎 피드백 저장 (질의응답 화면의 피드백 버튼에서 부름)
"""
from typing import Optional

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


def select_logs(user_id: str, session_id: Optional[str] = None) -> list[QALog]:
	"""
	질문 기록 조회하기 (최신순)

	user_id(필수)로 그 사람의 기록을 찾고, session_id를 주면 그 대화의 기록만 찾는다.
	- session_id가 None이면: 그 사람의 모든 대화 기록 (내 기록 화면의 목록용)
	- session_id가 있으면: 그 대화 하나의 기록만 (세션 복원·대화 이어가기용)

	순서
	1. sql: 기본 SELECT 문을 만든다 (WHERE user_id = %s)
	2. session_id가 있으면 "AND session_id = %s" 조건과 값을 하나 더 붙인다
	3. 맨 뒤에 ORDER BY created_at DESC를 붙여 최신 기록부터 나오게 한다
	   (같은 초에 저장된 기록은 log_id가 큰 것(나중에 저장한 것)이 먼저 나오게 log_id DESC도 붙임)
	4. get_connection()으로 실행하고 fetchall()로 모든 줄을 받는다 (줄마다 딕셔너리)
	5. 딕셔너리 한 줄씩 QALog로 바꿔 리스트에 담아서 돌려준다

	입력: user_id (아이디, 필수), session_id (대화 묶음 번호, 없으면 None)
	출력: list[QALog] (최신순, 기록이 없으면 빈 리스트 [])
	"""
	# 1) 기본 SQL (이 사람의 기록만)
	sql = """
		SELECT log_id, user_id, session_id, question, answer, persona, route,
			has_source, response_ms, tokens, cost_krw, feedback, error, created_at
		FROM qa_logs
		WHERE user_id = %s
	"""
	values = [user_id]

	# 2) session_id가 있으면 그 대화만
	if session_id != None:
		sql = sql + " AND session_id = %s"
		values.append(session_id)

	# 3) 최신순 정렬
	sql = sql + " ORDER BY created_at DESC, log_id DESC"

	# 4) 실행하고 모든 줄 받기
	with get_connection() as conn:
		cursor = conn.cursor()
		cursor.execute(sql, values)
		rows = cursor.fetchall()

	# 5) 한 줄씩 QALog로 바꾸기
	logs = []
	for row in rows:
		log = QALog(
			log_id=row["log_id"],
			user_id=row["user_id"],
			session_id=row["session_id"],
			question=row["question"],
			answer=row["answer"],
			persona=row["persona"],
			route=row["route"],
			has_source=row["has_source"],
			response_ms=row["response_ms"],
			tokens=row["tokens"],
			cost_krw=row["cost_krw"],
			feedback=row["feedback"],
			error=row["error"],
			created_at=row["created_at"]
		)
		logs.append(log)

	return logs


def update_feedback(log_id: int, feedback: int) -> int:
	"""
	피드백 저장하기 (👍/👎)

	답변별 👍(1)/👎(-1) 값을 qa_logs.feedback에 UPDATE 한다.
	- 어느 답변인지는 log_id(질문 기록 번호)로 찾는다 (on_feedback()이 state['last_log_id']를 넘겨줌)
	- 이미 피드백이 있던 답변이면 새 값으로 바뀐다 (👍 → 👎)

	순서
	1. sql: 바꿀 SQL을 만든다 (값 자리는 %s로 비워 둠)
	2. values: %s 자리에 순서대로 들어갈 값을 튜플로 만든다 (feedback, log_id 순서)
	3. get_connection()으로 DB에 연결해서 실행하고 commit으로 저장한다
	4. cursor.rowcount로 바뀐 줄 수를 받아서 돌려준다

	- 1, -1이 아닌 값은 DB 제약 조건(ck_qa_logs_feedback)이 막아서 에러가 난다
	- 없는 log_id이거나, 이미 같은 값이 저장돼 있으면 바뀐 줄이 없어서 0을 돌려준다

	입력: log_id (질문 기록 번호), feedback (👍 1 / 👎 -1)
	출력: int (바뀐 줄 수, 바뀌면 1)
	"""
	sql = """
		UPDATE qa_logs
		SET feedback = %s
		WHERE log_id = %s
	"""

	values = (feedback, log_id)

	with get_connection() as conn:
		cursor = conn.cursor()
		cursor.execute(sql, values)
		conn.commit()
		count = cursor.rowcount

	return count