"""외부 데이터 스키마 · Indicator, EcosChoice, EcosQuery, TermCard, ExchangeRate (엄정현)"""


from typing import Literal

from pydantic import BaseModel, Field


__all__ = ["Indicator", "EcosChoice", "EcosQuery", "TermCard", "ExchangeRate"]


class Indicator(BaseModel):
	"""[지표정보] 보고서에서 뽑은 지표 1개 (indicators 테이블 1행). LLM용 스키마에서는 report_id를 빼고 저장할 때 코드가 붙인다.
        예: '2026년 2분기 GDP 성장률 2.5%' 같은 구체적인 수치 지표를 나타냅니다.
	"""

	report_id: int | None =Field(
            default=None,
            description="연결된 보고서의 고유 ID 번호 (저장 전에는 비어있을 수 있음)",
        )
	name: str = Field(description="지표명 (INDICATOR_ALIASES로 통일한 이름)")
	value: float = Field(
            description="지표 이름 (예: 경제성장률, 실업률 등 표준화된 명칭)",
        )
	unit: str = Field(description="%, %p, 억 원, 조 원 등")
	period: str = Field(description="지표가 나타내는 기준 시점 (예: 2026Q2, 202607, 2025)")
	source: Literal["text", "table", "chart"] = Field(default="text", description="지표가 나타내는 기준 시점")
	needs_review: bool = Field(
		default="text",
		description ="수치가 정확한지 사람 검토가 필요한지 여부"
    )


class EcosChoice(BaseModel):
	"""LLM이 채우는 부분: INDICATOR_CODES의 지표 이름 하나와 고른 이유.

	name은 str로 두고, 후보에 있는지는 find_usable_data()가 INDICATOR_NAMES로 검사한다.
	(domain이 api.ecos_finder를 import하면 순환 import가 생기므로 Literal을 여기서 만들지 않는다.)
	
	[한국은행 지표 선택 결과] LLM이 사용자 보고서에 맞춰 어떤 ECOS 통계를 조회할지 고른 결과.
    한국은행 통계 중 어떤 지표를 선택했는지와 그 타당한 이유를 담습니다.
	"""

	name: str = Field(description="INDICATOR_CODES에 있는 지표 이름 중 하나")
	reason: str = Field(description="이 지표를 고른 이유")


class EcosQuery(BaseModel):
	"""코드가 채우는 부분: INDICATOR_CODES의 코드 + Indicator.period로 만든 기간.
	[한국은행 API 요청 조건] 한국은행(ECOS) OpenAPI를 실제로 호출할 때 사용하는 파라미터 규격.
	"""

	stat_code: str
	cycle: Literal["A", "Q", "M", "D"] = Field(description="A(연) · Q(분기) · M(월) · D(일)")
	item_code: str =Field(description ="통계표 내 첫 번째 항목코드")
	item_code2: str | None = Field(
		default=None,
		description="두 번째 항목코드 (예: 실업률 원계열 I28A). None이면 하위 항목이 모두 조회된다",
	)
	start: str
	end: str
	reason: str = ""


class TermCard(BaseModel):
	"""용어 풀이 카드: 사전 정의와 쉬운 맞춤형 설명 제공."""

	term: str = Field(description="설명할 경제 용어 단어")
	definition: str = Field(description="사전에서 가져온 원래의 정의 (terms 캐시 · ECOS 통계용어 · 표준국어대사전)")
	explanation: str = Field(description="원문 정의만 근거로 난이도에 맞춰 다시 쓴 2~3문장")
	source: str = Field(description="원문 정의의 출처 (예: ECOS 통계용어 / 표준국어대사전)")


class EcosExchangeRate(BaseModel):
	"""[환율 정보] 환율 1건. ECOS(get_ecos_exchange_rate)와 수출입은행(get_exchange_rate)이 같이 쓴다."""

	currency: str = Field(description="통화 종류 (예: USD · JPY(100엔) · EUR)")
	value: float =Field(description= "해당 통화의 원화 환율금액 (예: 1400.10)")
	base_date: str = Field(description="기준일 YYYYMMDD")