"""근거 기반 답변 프롬프트 · format_docs, has_context, build_messages (장유빈)"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from hri.domain.schemas.report import Chunk


def has_context(docs: list[Chunk]) -> bool:
	"""검색된 청크가 하나라도 있으면 True, 비어 있으면 False를 돌려준다. 

	hybrid_search()가 '키워드만 있고 의미 검색 0건'인 경우도 빈 리스트로 돌려주므로
	여기서는 비었는지만 본다. qa_graph의 grade 노드가 이 결과로 generate와
	no_answer 중 어디로 갈지 정한다.
	"""
	return bool(docs)