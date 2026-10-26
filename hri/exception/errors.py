"""공통 예외 · ChartExtractError, ExternalApiError (엄정현) / InvalidInputError (서동안) / OutputFormatError (김희진) / LoginFailedError, DuplicateUserError (임세준)"""

"""질의응답 예외 (exception.errors)."""


class InvalidInputError(Exception):
    """빈 질문·공백 입력·최대 길이(1,000자) 초과일 때 validate_question()이 발생시키는 예외."""