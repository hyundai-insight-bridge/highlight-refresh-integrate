"""질의응답 처리 · ask_stream (장유빈) / validate_question, mask_pii (서동안)"""

"""질의응답 서비스 중 입력 검증·개인정보 마스킹 (service.qa_service).

ask_stream()은 담당자가 같은 파일에 이어서 추가한다.
"""

import re

from hri.exception.errors import InvalidInputError

MAX_QUESTION_LENGTH = 1000

# 회원가입 정보(이름·아이디·비밀번호)만 가린다. 질문 안에서 라벨('이름:', '아이디는', '비번')
# 바로 뒤에 오는 값을 찾으며, 그룹 1은 라벨·구분 부분, 그룹 2는 가릴 값이다.
_SEP = r"\s*(?:(?:는|은|가|이)(?=[\s:=]))?\s*[:=]?\s*"  # 조사는 뒤에 공백이 있을 때만(이몽·가영 같은 이름 보호)
NAME_RE = re.compile(
    rf"((?:이름|성명){_SEP})(?!뭐|무엇|뭔|어떻)([가-힣]{{2,4}}?)"
    r"(?=입니다|이고|이에요|예요|이야|인데|이며|이다|이요|이라|(?![가-힣]))"
)
ID_RE = re.compile(rf"((?<![A-Za-z])(?:아이디|ID){_SEP})([A-Za-z0-9_.\-]{{3,}})", re.IGNORECASE)
PASSWORD_RE = re.compile(
    rf"((?<![A-Za-z])(?:비밀번호|비번|패스워드|암호|password|passwd|pwd|pw){_SEP})([!-~]+)",
    re.IGNORECASE,
)


def validate_question(question: str) -> str:
    """빈 입력·공백만 입력·최대 길이 초과면 InvalidInputError. 통과하면 앞뒤 공백을 뗀 질문을 반환한다."""
    question = question.strip()
    if not question:
        raise InvalidInputError("질문을 입력해 주세요.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise InvalidInputError(f"질문은 {MAX_QUESTION_LENGTH:,}자 이하로 입력해 주세요.")
    return question


def mask_pii(text: str) -> str:
    """이름(홍*동)·아이디(abc***)·비밀번호(********)를 가린다.

    LLM 호출 전과 qa_logs 저장 전에 사용한다. '이름: 홍길동'처럼 라벨이 붙은 값만 찾는다.
    """
    text = NAME_RE.sub(lambda m: m.group(1) + m.group(2)[0] + "*" * (len(m.group(2)) - 2) + m.group(2)[-1]
                       if len(m.group(2)) > 2 else m.group(1) + m.group(2)[0] + "*", text)
    text = ID_RE.sub(
        lambda m: m.group(1) + m.group(2)[:3 if len(m.group(2)) > 3 else 1]
        + "*" * (len(m.group(2)) - (3 if len(m.group(2)) > 3 else 1)),
        text,
    )
    return PASSWORD_RE.sub(lambda m: m.group(1) + "********", text)
