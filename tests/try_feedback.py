"""피드백 저장 테스트 (임세준) - 커밋하지 않는 파일

MySQL 대신 파이썬 기본 SQLite(메모리 DB)에 qa_logs를 잠깐 만들어서
진짜 update_feedback()의 SQL을 그대로 실행해 본다. (DB 설치·.env 필요 없음)

실행 (레포 맨 위 폴더에서):
	poetry run python -m tests.try_feedback

※ SQLite와 MySQL의 차이
	- 같은 값을 한 번 더 저장하면 MySQL은 바뀐 줄이 없어서 0, SQLite는 찾은 줄 수라서 1이 나온다
	  (그래서 이 경우는 이 테스트에서 확인하지 않음)
"""
import sqlite3

from hri.dao import qa_log_dao
from hri.dao.qa_log_dao import update_feedback


# ----------------------------------------------------------------
# 1. 메모리 DB 만들기 (feedback 제약 조건은 sql/schema.sql과 같게)
# ----------------------------------------------------------------
def dict_row(cursor, row):
	"""pymysql DictCursor처럼 줄마다 딕셔너리로 돌려주기"""
	result = {}
	for i in range(len(cursor.description)):
		result[cursor.description[i][0]] = row[i]
	return result


db = sqlite3.connect(":memory:")
db.row_factory = dict_row

db.executescript("""
	CREATE TABLE qa_logs (
		log_id INTEGER PRIMARY KEY AUTOINCREMENT,
		user_id TEXT, session_id TEXT, question TEXT, answer TEXT, route TEXT,
		feedback INTEGER NULL,
		CONSTRAINT ck_qa_logs_feedback CHECK (feedback IS NULL OR feedback IN (1, -1))
	);
	INSERT INTO qa_logs (user_id, session_id, question, answer, route) VALUES ('kim', 's-1', '기준금리 전망은?', '2.5%입니다.', 'rag');
	INSERT INTO qa_logs (user_id, session_id, question, answer, route) VALUES ('kim', 's-1', '환율은?', '1,390원입니다.', 'rag');
""")


class FakeCursor:
	"""MySQL의 값 자리 %s를 SQLite의 ?로 바꿔서 실행해 주는 커서"""

	def __init__(self):
		self.cursor = db.cursor()
		self.rowcount = 0

	def execute(self, sql, values=()):
		self.cursor.execute(sql.replace("%s", "?"), values)
		self.rowcount = self.cursor.rowcount


class FakeConnection:
	"""with get_connection() as conn: 모양 그대로 쓸 수 있게 감싼 것"""

	def __enter__(self):
		return self

	def __exit__(self, *args):
		return False

	def cursor(self):
		return FakeCursor()

	def commit(self):
		db.commit()


qa_log_dao.get_connection = lambda: FakeConnection()


def get_feedback(log_id):
	"""DB에 저장된 feedback 값 꺼내 보기"""
	row = db.execute("SELECT feedback FROM qa_logs WHERE log_id = ?", (log_id,)).fetchone()
	return row["feedback"]


# ----------------------------------------------------------------
# 2. 테스트 함수
# ----------------------------------------------------------------
passed = 0
total = 0


def check(name, ok, info=""):
	global passed, total
	total = total + 1
	if ok:
		passed = passed + 1
		print(f"✅ {name} {info}")
	else:
		print(f"❌ {name} {info}")


# ----------------------------------------------------------------
# 3. 확인
# ----------------------------------------------------------------
check("1 처음에는 피드백 없음 (NULL)", get_feedback(1) == None and get_feedback(2) == None)

count = update_feedback(1, 1)
check("2 👍 저장 → 바뀐 줄 1", count == 1, count)
check("3 1번 답변 feedback = 1", get_feedback(1) == 1, get_feedback(1))
check("4 다른 답변(2번)은 그대로 NULL", get_feedback(2) == None, get_feedback(2))

count = update_feedback(1, -1)
check("5 👍 → 👎로 바꾸기 → 바뀐 줄 1", count == 1 and get_feedback(1) == -1, get_feedback(1))

count = update_feedback(999, 1)
check("6 없는 log_id → 0", count == 0, count)

try:
	update_feedback(2, 2)
	check("7 1·-1이 아닌 값은 DB 제약 조건이 막음", False)
except Exception as e:
	check("7 1·-1이 아닌 값은 DB 제약 조건이 막음", get_feedback(2) == None, type(e).__name__)

print(f"\n통과 {passed}/{total}")