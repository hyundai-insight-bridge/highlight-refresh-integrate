"""환경 설정 로드 · load_settings (임세준)"""
import os
from functools import lru_cache

from dotenv import load_dotenv

from hri.domain.schemas import Settings


def _require(name: str) -> str:
	"""필수 환경 변수를 읽는다. 없거나 비어 있으면 어떤 키가 빠졌는지 알려준다."""
	value = os.getenv(name)
	if not value:
		raise RuntimeError(f"{name}이(가) .env에 없습니다. .env.example을 참고해 추가하세요.")
	return value


@lru_cache(maxsize=1)
def load_settings() -> Settings:
	"""
	.env를 읽어 Settings를 만든다.

	처음 한 번만 읽고 캐시한다. 테스트에서 환경 변수를 바꿨다면 load_settings.cache_clear()를 호출한다.
	현재는 MySQL·Chroma 연결 항목만 읽는다. 다른 항목은 Settings에 필드를 추가한 뒤 여기서 함께 읽는다.
	"""
	load_dotenv()
	chroma_mode = os.getenv("CHROMA_MODE", "http")
	return Settings(
		mysql_host=_require("MYSQL_HOST"),
		mysql_port=os.getenv("MYSQL_PORT", "3306"),
		mysql_user=_require("MYSQL_USER"),
		mysql_password=_require("MYSQL_PASSWORD"),
		mysql_database=_require("MYSQL_DATABASE"),
		chroma_mode=chroma_mode,
		chroma_host=_require("CHROMA_HOST") if chroma_mode == "http" else os.getenv("CHROMA_HOST", "localhost"),
		chroma_port=os.getenv("CHROMA_PORT", "8000"),
		chroma_persist_path=os.getenv("CHROMA_PERSIST_PATH", "chroma_db/"),
		chroma_collection=os.getenv("CHROMA_COLLECTION", "hri_reports"),
	)
