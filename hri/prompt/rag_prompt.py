"""근거 기반 답변 프롬프트 · format_docs, has_context, build_messages (장유빈)"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from hri.domain.schemas.qa import ContextDoc
	from hri.domain.schemas.report import Chunk

def format_docs(docs: list[ContextDoc]) -> str:
	"""
	검색된 근거(ContextDoc) 목록을 프롬프트의 [자료] 문자열로 만든다.

	근거마다 '[출처: 보고서명 p.시작-끝 / 섹션명]' 한 줄을 맨 위에 붙이고 그 아래에 본문을 둔다.
	차트(kind='chart')는 '[출처: 보고서명 p.페이지 / 그림 (차트 OCR)]'로 구분하고,
	needs_review=True인 근거는 출처 줄 끝에 '(추정값)'을 붙인다.
	근거 사이는 빈 줄로 나누고, 근거가 없으면 빈 문자열을 돌려준다.
	"""
	blocks = []
	for doc in docs:
		if doc.kind == "chart":
			figure = doc.caption or "그림"
			header = f"[출처: {doc.report_title} p.{doc.page_start} / {figure} (차트 OCR)]"
		else:
			header = f"[출처: {doc.report_title} p.{doc.page_start}-{doc.page_end}"
			if doc.section_title:
				header += f" / {doc.section_title}"
			header += "]"
		if doc.needs_review:
			header += " (추정값)"
		blocks.append(f"{header}\n{doc.text}")
	return "\n\n".join(blocks)
# 코드를 읽는 순서는 이래요.
# 근거(doc)를 하나씩 돌아요.
# 차트면 [출처: ... (차트 OCR)], 아니면 [출처: ... p.시작-끝 / 섹션명] 줄(header)을 만들어요.
# needs_review가 참이면 줄 끝에 (추정값)을 붙여요.
# header와 본문을 붙여 blocks에 넣고, 마지막에 빈 줄로 이어 붙여요.


def has_context(docs: list[Chunk]) -> bool:
	"""검색된 청크가 하나라도 있으면 True, 비어 있으면 False를 돌려준다. 

	hybrid_search()가 '키워드만 있고 의미 검색 0건'인 경우도 빈 리스트로 돌려주므로
	여기서는 비었는지만 본다. qa_graph의 grade 노드가 이 결과로 generate와
	no_answer 중 어디로 갈지 정한다.
	"""
	return bool(docs)