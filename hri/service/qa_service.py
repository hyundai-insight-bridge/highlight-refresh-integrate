"""질의응답 처리 · ask_stream (장유빈) / validate_question, mask_pii (서동안)"""

"""질의응답 서비스 중 입력 검증·개인정보 마스킹 (service.qa_service).

ask_stream()은 담당자가 같은 파일에 이어서 추가한다.
"""

import re

from hri.exception.errors import InvalidInputError

MAX_QUESTION_LENGTH = 1000

# 010-1234-5678 · 01012345678 · 02-123-4567 처럼 0으로 시작하는 국내 전화번호
PHONE_RE = re.compile(r"(?<!\d)(0\d{1,2})([-.\s]?)(\d{3,4})([-.\s]?)(\d{4})(?!\d)")
EMAIL_RE = re.compile(r"([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)")


def validate_question(question: str) -> str:
    """빈 입력·공백만 입력·최대 길이 초과면 InvalidInputError. 통과하면 앞뒤 공백을 뗀 질문을 반환한다."""
    question = question.strip()
    if not question:
        raise InvalidInputError("질문을 입력해 주세요.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise InvalidInputError(f"질문은 {MAX_QUESTION_LENGTH:,}자 이하로 입력해 주세요.")
    return question


def mask_pii(text: str) -> str:
    """이메일(ki***@naver.com)과 전화번호(010-****-6789)를 가린다.

    LLM 호출 전과 qa_logs 저장 전에 사용한다. 이메일을 먼저 가려야 주소 안의 숫자가 전화번호로 잡히지 않는다.
    """
    text = EMAIL_RE.sub(
        lambda m: f"{m.group(1)[:2] if len(m.group(1)) > 2 else m.group(1)[:1]}***@{m.group(2)}",
        text,
    )
    return PHONE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}****{m.group(4)}{m.group(5)}", text)
