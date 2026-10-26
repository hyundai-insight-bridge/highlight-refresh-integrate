"""공통 예외 · ChartExtractError, ExternalApiError (엄정현) / InvalidInputError (서동안) / OutputFormatError (김희진) / LoginFailedError, DuplicateUserError (임세준)"""

# (엄정현) 보고서 파일 올라왔ㅇ르때 OCR과 vision medel이 구조화 실패한 경우.
class ChartExtractError(Exception):
	"""차트 잘라내기·OCR·Vision 구조화가 실패했을 때 발생하는 예외.

	extract_charts()·ocr_chart()·chart_to_table()에서 raise하고, process_charts 노드가 잡아서
	업로드 전체를 멈추지 않고 그 차트만 건너뛴 뒤 warnings에 str(예외)를 기록한다.
	예) raise ChartExtractError("5쪽 차트: Vision 응답을 ChartData로 바꾸지 못함")
	"""