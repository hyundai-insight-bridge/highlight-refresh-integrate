"""설정 스키마 · Settings: .env에서 읽은 앱 설정, 현재는 MySQL·Chroma 연결 항목만 (임세준)"""
from typing import Literal

from pydantic import BaseModel, SecretStr

__all__ = ["Settings"]


class Settings(BaseModel):
	"""
	앱 설정 모델.

	MySQL·Chroma는 서버에 띄운 것에 연결만 한다(서버 실행은 이 프로젝트에서 다루지 않음).
	API 키·모델·OCR·그래프·업로드 한도·검색 설정 필드는 담당자가 이어서 추가한다.
	"""

	# MySQL
	mysql_host: str
	mysql_port: int = 3306
	mysql_user: str
	mysql_password: SecretStr
	mysql_database: str

	# Chroma: http = 서버(HttpClient), persistent = 로컬 경로(PersistentClient, 테스트·오프라인용)
	chroma_mode: Literal["http", "persistent"] = "http"
	chroma_host: str = "localhost"
	chroma_port: int = 8000
	chroma_persist_path: str = "chroma_db/"
	chroma_collection: str = "hri_reports"
