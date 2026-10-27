"""공통 예외 · ChartExtractError, ExternalApiError (엄정현) / InvalidInputError (서동안) / OutputFormatError (김희진) / LoginFailedError, DuplicateUserError (임세준)"""

# (엄정현) 보고서 파일 올라왔을때 OCR과 vision medel이 구조화 실패한 경우.
class ChartExtractError(Exception):
	"""차트 잘라내기·OCR·Vision 구조화가 실패했을 때 발생하는 예외.

	extract_charts()·ocr_chart()·chart_to_table()에서 raise하고, process_charts 노드가 잡아서
	업로드 전체를 멈추지 않고 그 차트만 건너뛴 뒤 warnings에 str(예외)를 기록한다.
	예) raise ChartExtractError("5쪽 차트: Vision 응답을 ChartData로 바꾸지 못함")
	"""
"""질의응답 예외 (exception.errors)."""


class InvalidInputError(Exception):
    """빈 질문·공백 입력·최대 길이(1,000자) 초과일 때 validate_question()이 발생시키는 예외."""



class LoginFailedError(Exception):
	"""로그인 실패 (아이디가 없거나 비밀번호가 다를 때)"""
	pass


class DuplicateUserError(Exception):
	"""회원가입 실패 (이미 사용 중인 아이디일 때)"""
	pass
