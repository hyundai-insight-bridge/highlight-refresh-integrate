"""Chroma 연결·청크 저장 · get_collection, add_chunks, delete_report_vectors (김희진)"""
from functools import lru_cache

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

from hri.config.settings import load_settings


@lru_cache(maxsize=1)
def _get_client() -> ClientAPI:
	"""
	CHROMA_MODE에 따라 Chroma 클라이언트를 한 번만 만든다.

	- http: 서버에 띄운 Chroma에 HttpClient로 연결 (기본값)
	- persistent: 로컬 경로에 저장하는 PersistentClient (테스트·오프라인용)
	"""
	settings = load_settings()
	if settings.chroma_mode == "persistent":
		return chromadb.PersistentClient(path=settings.chroma_persist_path)
	return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def get_collection() -> Collection:
	"""
	보고서 청크 컬렉션을 가져온다. 없으면 코사인 거리로 만든다.

	임베딩은 embed_texts()로 직접 만들어 넣으므로 Chroma 기본 임베딩 함수는 쓰지 않는다
	(embedding_function=None).
	"""
	settings = load_settings()
	return _get_client().get_or_create_collection(
		name=settings.chroma_collection,
		metadata={"hnsw:space": "cosine"},
		embedding_function=None,
	)
