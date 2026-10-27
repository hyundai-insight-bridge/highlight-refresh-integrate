"""Chroma 연결·청크 저장·삭제 테스트 · tmp_path의 로컬 Chroma 사용, 임베딩은 가짜 (김희진)"""
from types import SimpleNamespace
import pytest
from hri.domain.schemas import Chunk
from hri.vector_store import chroma_store

def _fake_embed(texts):
	"""텍스트마다 [글자 수, 1.0, 0.0] 3차원 벡터를 돌려준다. 호출 기록은 calls에 남긴다."""
	_fake_embed.calls.append(list(texts))
	return [[float(len(t)), 1.0, 0.0] for t in texts]

@pytest.fixture
def store(monkeypatch, tmp_path):
	"""persistent 모드 설정 + 가짜 임베딩. 테스트마다 새 폴더를 쓴다."""
	_fake_embed.calls = []
	settings = SimpleNamespace(
		chroma_mode="persistent",
		chroma_persist_path=str(tmp_path / "chroma"),
		chroma_collection="test_reports",
		chroma_host="localhost",
		chroma_port=8000,
	)
	monkeypatch.setattr(chroma_store, "load_settings", lambda: settings)
	monkeypatch.setattr(chroma_store, "embed_texts", _fake_embed)
	return settings

def _chunk(report_id=1, chunk_no=0, text="본문", **kwargs):
	"""테스트용 Chunk. 기본은 텍스트 청크."""
	return Chunk(
		report_id=report_id,
		chunk_no=chunk_no,
		section_no=kwargs.pop("section_no", 0),
		page=kwargs.pop("page", 1),
		text=text,
		**kwargs,
	)

# ---------- get_collection ----------
def test_get_collection_persistent_uses_settings(store):
	collection = chroma_store.get_collection()
	assert collection.name == "test_reports"
	assert collection.metadata["hnsw:space"] == "cosine"

def test_get_collection_returns_same_data_on_second_call(store):
	chroma_store.add_chunks([_chunk()])
	# 두 번째 호출은 새 클라이언트로 같은 컬렉션을 다시 가져온다
	assert chroma_store.get_collection().count() == 1

def test_get_collection_http_mode_passes_host_and_port(store, monkeypatch):
	store.chroma_mode = "http"
	store.chroma_host = "chroma.example"
	store.chroma_port = 9000
	captured = {}

	class _FakeClient:
		def get_or_create_collection(self, **kwargs):
			captured["collection_kwargs"] = kwargs
			return "collection"

	def fake_http_client(host, port):
		captured["host"] = host
		captured["port"] = port
		return _FakeClient()

	monkeypatch.setattr(chroma_store.chromadb, "HttpClient", fake_http_client)
	assert chroma_store.get_collection() == "collection"
	assert (captured["host"], captured["port"]) == ("chroma.example", 9000)
	assert captured["collection_kwargs"]["name"] == "test_reports"
	assert captured["collection_kwargs"]["metadata"] == {"hnsw:space": "cosine"}
	assert captured["collection_kwargs"]["embedding_function"] is None

# ---------- add_chunks ----------
def test_add_chunks_returns_count_and_stores_ids(store):
	chunks = [_chunk(chunk_no=0, text="가"), _chunk(chunk_no=1, text="나나")]
	assert chroma_store.add_chunks(chunks) == 2
	saved = chroma_store.get_collection().get()
	assert sorted(saved["ids"]) == ["1-0", "1-1"]

def test_add_chunks_stores_documents_and_embeddings(store):
	chroma_store.add_chunks([_chunk(chunk_no=0, text="세글자")])
	saved = chroma_store.get_collection().get(include=["documents", "embeddings"])
	assert saved["documents"] == ["세글자"]
	assert list(saved["embeddings"][0]) == [3.0, 1.0, 0.0]

def test_add_chunks_text_chunk_metadata_omits_none(store):
	chroma_store.add_chunks([_chunk(chunk_no=0, page=3, section_no=2)])
	metadata = chroma_store.get_collection().get()["metadatas"][0]
	assert metadata == {
		"report_id": 1, "page": 3, "section_no": 2, "chunk_no": 0, "chunk_type": "text",
	}

def test_add_chunks_table_chunk_keeps_doc_id_and_category(store):
	chunk = _chunk(chunk_no=1, text="[표 1] 요약", chunk_type="table", category="금리", doc_id="doc-1")
	chroma_store.add_chunks([chunk])
	metadata = chroma_store.get_collection().get()["metadatas"][0]
	assert metadata["chunk_type"] == "table"
	assert metadata["category"] == "금리"
	assert metadata["doc_id"] == "doc-1"

def test_add_chunks_empty_returns_zero_without_embedding(store):
	assert chroma_store.add_chunks([]) == 0
	assert _fake_embed.calls == []
	assert chroma_store.get_collection().count() == 0

def test_add_chunks_report_id_none_raises_and_saves_nothing(store):
	chunks = [_chunk(chunk_no=0), _chunk(report_id=None, chunk_no=1)]
	with pytest.raises(ValueError):
		chroma_store.add_chunks(chunks)
	assert _fake_embed.calls == []
	assert chroma_store.get_collection().count() == 0

def test_add_chunks_batches_by_100(store):
	chunks = [_chunk(chunk_no=i, text="x") for i in range(250)]
	assert chroma_store.add_chunks(chunks) == 250
	assert [len(call) for call in _fake_embed.calls] == [100, 100, 50]
	assert chroma_store.get_collection().count() == 250

def test_add_chunks_keeps_reports_separate(store):
	chroma_store.add_chunks([_chunk(report_id=1, chunk_no=0), _chunk(report_id=2, chunk_no=0)])
	saved = chroma_store.get_collection().get()
	assert sorted(saved["ids"]) == ["1-0", "2-0"]

# ---------- delete_report_vectors ----------
def test_delete_report_vectors_removes_only_that_report(store):
	chroma_store.add_chunks([
		_chunk(report_id=1, chunk_no=0), _chunk(report_id=1, chunk_no=1),
		_chunk(report_id=2, chunk_no=0),
	])
	chroma_store.delete_report_vectors(1)
	assert chroma_store.get_collection().get()["ids"] == ["2-0"]

def test_delete_report_vectors_missing_report_is_noop(store):
	chroma_store.add_chunks([_chunk(report_id=1, chunk_no=0)])
	chroma_store.delete_report_vectors(999)  # 없는 보고서: 오류 없이 끝나야 함
	assert chroma_store.get_collection().count() == 1

def test_delete_report_vectors_on_empty_collection(store):
	chroma_store.delete_report_vectors(1)
	assert chroma_store.get_collection().count() == 0

def test_add_after_delete_allows_reupload(store):
	chroma_store.add_chunks([_chunk(report_id=1, chunk_no=0, text="옛 본문")])
	chroma_store.delete_report_vectors(1)
	chroma_store.add_chunks([_chunk(report_id=1, chunk_no=0, text="새 본문")])
	assert chroma_store.get_collection().get()["documents"] == ["새 본문"]