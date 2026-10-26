"""설정 스키마 · Settings: .env에서 읽은 앱 설정 (임세준)"""
from typing import Literal, Optional

from pydantic import BaseModel, SecretStr

__all__ = ["Settings"]


class Settings(BaseModel):
	"""
	앱 설정 모델.

	MySQL·Chroma는 서버에 띄운 것에 연결만 한다(서버 실행은 이 프로젝트에서 다루지 않음).
	API 키·모델·OCR·그래프·업로드 한도·검색 설정 필드는 담당자가 이어서 추가한다.
	"""
	# API 키 (없으면 빈 문자열)
	openai_api_key: str = ""
	ecos_api_key: str = ""
	stdict_api_key: str = ""
	koreaexim_api_key: str = ""

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

	# 모델·단가
	llm_model: str = "gpt-4o-mini"
	vision_model: str = "gpt-4o"
	model_prices: str = '{"gpt-4o-mini": {"input": 0.15, "output": 0.60}}'

	# OCR·차트
	ocr_langs: str = "ko,en"
	ocr_min_conf: float = 0.4
	chart_dpi: int = 200
	min_chart_pt: int = 120

	# 그래프
	graph_recursion_limit: int = 8

	# 업로드 한도
	max_mb: int = 30
	max_pages: int = 150

	# 검색
	chunk_size: int = 500
	chunk_overlap: int = 50
	threshold: float = 0.3
	max_context_chars: Optional[int] = None