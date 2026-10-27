"""공통 LLM 모듈 · get_chat_model (서동안), cost_korean_won, get_usd_krw (임세준)

- get_chat_model(): ChatOpenAI 모델을 만들어 반환 (서동안)
- cost_korean_won(): 토큰 사용량을 원화 비용으로 환산 (임세준)
- get_usd_krw(): 원/달러 환율 조회, 실패하면 1,400원 (임세준)
"""

import json

from langchain_core.messages.ai import UsageMetadata
from langchain_openai import ChatOpenAI

from hri.config.settings import load_settings

# 환율을 가져오지 못했을 때 쓰는 기본 원/달러 환율
DEFAULT_USD_KRW = 1400.0

"""기본 모델은 hri.Settings.llm_model에서 가져온다. 모델을 바꿀 때는 Settings(.env)만 수정한다."""
MODEL = load_settings().llm_model


def get_chat_model(
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 500,
) -> ChatOpenAI:
    """ChatOpenAI 모델을 만들어 반환한다."""
    return ChatOpenAI(
        model=model or MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        stream_usage=True,
    )


def ask_llm(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 500,
) -> tuple[str, UsageMetadata]:
    """자유 텍스트 응답용. 답변 텍스트와 usage_metadata를 반환한다."""
    response = get_chat_model(temperature=temperature, max_tokens=max_tokens).invoke(messages)
    return response.content, response.usage_metadata


def chat_bot(question: str) -> str:
    """잡담 응대 (qa_graph의 chat 노드: route_question이 'chat'으로 분류한 경우).

    검색 없이 1~2문장으로 친절히 답하고, 보고서 질문이면 보고서를 선택해 질문하도록 안내한다.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "당신은 경제 분석 보고서 요약 서비스의 안내 도우미입니다. "
                "인사·감사·잡담에는 검색 없이 1~2문장으로 친절하게 답합니다. "
                "경제 보고서 내용에 대한 질문이면 답하지 말고, "
                "화면에서 보고서를 선택한 뒤 질문해 달라고 안내합니다."
            ),
        },
        {"role": "user", "content": question},
    ]
    answer, _ = ask_llm(messages)
    return answer


def cost_korean_won(usage: dict[str, UsageMetadata], usd_to_krw: float) -> float:
	"""
	토큰 사용량을 원화 비용으로 바꾸기

	usage는 그래프를 실행하는 동안 UsageMetadataCallbackHandler가 모은 모델별 토큰 수이다.
	예) {"gpt-5-mini-2025-08-07": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500}}

	계산 방법 (모델마다 계산해서 모두 더함)
	- 달러 = 입력 토큰 / 1,000,000 × 입력 단가 + 출력 토큰 / 1,000,000 × 출력 단가
	- 원화 = 달러 × usd_to_krw(원/달러 환율)
	단가는 .env의 MODEL_PRICES(1M 토큰당 USD)에서 읽는다.

	- OpenAI는 모델 이름 뒤에 날짜를 붙여서 알려 준다 ("gpt-5-mini-2025-08-07").
	  그래서 단가표의 이름("gpt-5-mini")으로 시작하는지 보고 단가를 찾는다.
	- 단가표에 없는 모델은 0원으로 계산한다.
	- DB에 저장하지 않고 계산만 하는 함수다 (저장은 insert_usage, save_qa_log가 함)

	입력: usage (모델별 토큰 수 딕셔너리), usd_to_krw (원/달러 환율, get_usd_krw()로 받은 값)
	출력: float (원화 비용, 소수점 넷째 자리까지)
	"""
	# 모델별 단가표 (글자로 저장돼 있어서 딕셔너리로 바꿈)
	settings = load_settings()
	prices = json.loads(settings.model_prices)

	total_won = 0.0

	for model_name in usage:
		tokens = usage[model_name]
		input_tokens = tokens["input_tokens"]
		output_tokens = tokens["output_tokens"]

		# 단가표에서 이 모델의 단가 찾기
		price = None
		for price_name in prices:
			if model_name.startswith(price_name):
				price = prices[price_name]

		# 단가가 없으면 0원으로 하고 넘어감
		if price == None:
			continue

		# 1M 토큰당 USD 단가로 달러 계산
		dollar = input_tokens / 1000000 * price["input"] + output_tokens / 1000000 * price["output"]

		# 달러를 원화로 바꿔서 더하기
		total_won = total_won + dollar * usd_to_krw

	return round(total_won, 4)


def get_usd_krw() -> float:
	"""
	원/달러 환율 가져오기

	한국은행 ECOS API(get_ecos_exchange_rate)로 최근 원/달러 환율을 가져온다.
	가져오지 못하면 기본 환율 1,400원을 쓴다.
	(캐시를 쓰지 않아서 부를 때마다 새로 가져온다)

	- get_ecos_exchange_rate()는 엄정현 님 담당(외부데이터)이라 아직 없을 수도 있다.
	  그래서 함수 안에서 불러오고, 없거나 에러가 나도 1,400원으로 계속 동작한다.

	입력: 없음
	출력: float (원/달러 환율)
	"""
	try:
		from hri.api.ecos_client import get_ecos_exchange_rate

		rate = get_ecos_exchange_rate("USD")
		usd_krw = float(rate.value)
	except Exception:
		usd_krw = DEFAULT_USD_KRW

	return usd_krw