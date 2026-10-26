"""공통 LLM 모듈 (llm.llm_client)."""

from langchain_core.messages.ai import UsageMetadata
from langchain_openai import ChatOpenAI

from hri.config.settings import load_settings

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
