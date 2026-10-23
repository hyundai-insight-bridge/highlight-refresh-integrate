"""MySQL 연결 · get_connection (장유빈)"""
import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from hri.config.settings import load_settings


def get_connection() -> Connection:
	"""
	서버에 띄운 MySQL에 새 연결을 만든다.

	with 문으로 쓰면 블록이 끝날 때 연결이 닫힌다. autocommit이 꺼져 있으므로
	쓰기 작업은 호출부에서 commit()·rollback()을 직접 호출한다.

	사용 예:
		with get_connection() as conn:
			with conn.cursor() as cur:
				cur.execute("SELECT 1")
				row = cur.fetchone()
	"""
	settings = load_settings()
	return pymysql.connect(
		host=settings.mysql_host,
		port=settings.mysql_port,
		user=settings.mysql_user,
		password=settings.mysql_password.get_secret_value(),
		database=settings.mysql_database,
		charset="utf8mb4",
		cursorclass=DictCursor,
		connect_timeout=10,
	)
