"""대화 유지 · trim_history, rewrite_question (장유빈)"""

from langchain_core.messages import BaseMessage, trim_messages


def trim_history(history: list[BaseMessage], max_turns: int = 6) -> list[BaseMessage]:
	"""대화 기록에서 최근 max_turns턴만 남겨 토큰 한도와 비용을 지킨다.

	한 턴은 사용자 질문과 답변 한 쌍(메시지 2개)이다. 메시지 개수를 기준으로
	최근 것부터 max_turns * 2개만 남기고, 항상 사용자 메시지(human)로 시작하도록
	앞부분을 자른다. system 메시지는 build_messages()에서 맨 앞에 따로 넣는다.
	"""
	return trim_messages(
		history,
		strategy="last",
		token_counter=len,
		max_tokens=max_turns * 2,
		start_on="human",
	)