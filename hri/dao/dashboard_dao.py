"""대시보드 1차 SQL · select_top_questions, select_source_ratio, select_perf_cost, select_recent_errors (임세준)

관리자 대시보드 1차 화면에 보여 줄 값을 qa_logs·llm_usage 테이블에서 집계하는 DAO.
get_dashboard_data()(3.7.8)가 이 함수들의 결과를 화면 형식으로 가공한다.
- select_top_questions(): 많이 물어본 질문 TOP 10
- select_source_ratio(): '자료에 없습니다'(no_answer) 응답 비율
- select_perf_cost(): 일자별 평균 응답 시간 + flow·모델별 토큰 합계 (원화 비용은 DB에 저장하지 않고 get_dashboard_data()에서 계산)
- select_recent_errors(): 최근 에러 기록 20건
"""
from hri.dao.db import get_connection


def select_top_questions() -> list[dict]:
	"""
	질문 TOP 10 조회

	qa_logs를 question으로 GROUP BY 하여 COUNT 내림차순 상위 10건을 가져온다.
	(같은 질문을 몇 번 했는지 세서 많이 나온 순서로 10개)

	입력: 없음
	출력: list[dict] (예: [{'question': '기준금리 전망은?', 'count': 5}, ...], 기록이 없으면 [])
	"""
	sql = """
		SELECT question, COUNT(*) AS count
		FROM qa_logs
		GROUP BY question
		ORDER BY count DESC
		LIMIT 10
	"""

	with get_connection() as conn:
		cursor = conn.cursor()
		cursor.execute(sql)
		rows = cursor.fetchall()

	# fetchall()이 튜플로 줄 수 있어서 리스트로 바꿔서 돌려줌
	return list(rows)


def select_source_ratio() -> float:
	"""
	자료 유무 응답 비율 조회 ('자료에 없습니다' 응답 비율)

	route IN ('rag', 'no_answer')인 답변 중 route = 'no_answer'의 비율을
	AVG(CASE WHEN ...)로 계산한다. (잡담(chat)·오류(error)는 제외)
	- no_answer면 1, rag면 0으로 바꾼 뒤 평균을 내면 no_answer의 비율이 된다
	  예) rag 3개 + no_answer 1개 → (0+0+0+1) / 4 = 0.25

	입력: 없음
	출력: float (0.0 ~ 1.0, 소수점 넷째 자리까지, 해당 답변이 하나도 없으면 0.0)
	"""
	sql = """
		SELECT AVG(CASE WHEN route = 'no_answer' THEN 1 ELSE 0 END) AS ratio
		FROM qa_logs
		WHERE route IN ('rag', 'no_answer')
	"""

	with get_connection() as conn:
		cursor = conn.cursor()
		cursor.execute(sql)
		row = cursor.fetchone()

	# 해당 답변이 하나도 없으면 AVG 결과가 NULL(None)
	if row["ratio"] == None:
		return 0.0

	return float(row["ratio"])


def select_perf_cost() -> list[dict]:
	"""
	응답 시간·토큰 조회 (원화 비용 계산용 재료)

	일자별 평균 응답 시간(qa_logs AVG)과 llm_usage의 flow·모델별 토큰 합계(SUM)를 집계한다.
	원화 비용은 DB에 저장하지 않으므로 여기서는 토큰만 모으고,
	get_dashboard_data()가 cost_korean_won()으로 원화 비용을 계산해 대시보드에만 보여 준다.

	순서
	1. llm_usage를 날짜·flow·모델별로 묶어 입력 토큰·출력 토큰을 SUM 한다 (u)
	   (모델마다 단가가 달라서 모델별로 나눠 둬야 원화 비용을 계산할 수 있음)
	2. qa_logs를 날짜별로 묶어 응답 시간을 AVG 한다 (q)
	3. 두 결과를 날짜로 LEFT JOIN 해서 한 줄에 함께 담는다
	   (질문이 없던 날은 평균 응답 시간이 None)
	4. 최근 날짜부터, 같은 날은 flow 순서(qa → ingest → summary → agent, DB ENUM 순서)·모델 이름 순으로 정렬한다
	5. DB가 돌려준 Decimal(소수 타입) 값을 int·float로 바꿔서 돌려준다

	입력: 없음
	출력: list[dict]
	      예) [{'day': date(2026, 10, 28), 'flow': 'qa', 'model': 'gpt-5-mini-2025-08-07',
	            'input_tokens': 1200, 'output_tokens': 300, 'avg_response_ms': 1534.5}, ...]
	"""
	sql = """
		SELECT u.day, u.flow, u.model, u.input_tokens, u.output_tokens, q.avg_response_ms
		FROM (
			SELECT DATE(created_at) AS day, flow, model,
				SUM(input_tokens) AS input_tokens,
				SUM(output_tokens) AS output_tokens
			FROM llm_usage
			GROUP BY DATE(created_at), flow, model
		) AS u
		LEFT JOIN (
			SELECT DATE(created_at) AS day, AVG(response_ms) AS avg_response_ms
			FROM qa_logs
			GROUP BY DATE(created_at)
		) AS q
		ON u.day = q.day
		ORDER BY u.day DESC, u.flow, u.model
	"""

	with get_connection() as conn:
		cursor = conn.cursor()
		cursor.execute(sql)
		rows = cursor.fetchall()

	# Decimal → int·float로 바꾸기
	results = []
	for row in rows:
		avg_response_ms = row["avg_response_ms"]
		if avg_response_ms != None:
			avg_response_ms = round(float(avg_response_ms), 1)

		results.append({
			"day": row["day"],
			"flow": row["flow"],
			"model": row["model"],
			"input_tokens": int(row["input_tokens"]),
			"output_tokens": int(row["output_tokens"]),
			"avg_response_ms": avg_response_ms
		})

	return results


def select_recent_errors() -> list[dict]:
	"""
	최근 에러 로그 조회

	route = 'error'이거나 error 컬럼이 NULL이 아닌 기록을 최신순 20건 가져온다.
	(같은 시각에 저장된 기록은 나중에 저장된 것(log_id가 큰 것)이 먼저 오게 함)

	입력: 없음
	출력: list[dict] (예: [{'log_id': 7, 'user_id': 'kim', 'question': '', 'route': 'error',
	                       'error': '빈 질문', 'created_at': datetime(...)}, ...], 없으면 [])
	"""
	sql = """
		SELECT log_id, user_id, question, route, error, created_at
		FROM qa_logs
		WHERE route = 'error' OR error IS NOT NULL
		ORDER BY created_at DESC, log_id DESC
		LIMIT 20
	"""

	with get_connection() as conn:
		cursor = conn.cursor()
		cursor.execute(sql)
		rows = cursor.fetchall()

	return list(rows)