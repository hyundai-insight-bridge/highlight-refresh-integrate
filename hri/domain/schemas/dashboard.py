"""대시보드 스키마 · DashboardData (임세준)"""

from pydantic import BaseModel

__all__ = ["DashboardData"]


class DashboardData(BaseModel):
	"""관리자 대시보드에 보여줄 데이터"""

	top_questions: str  # 질문 TOP 10 (마크다운 표)
	source_ratio: float  # 자료 유무 응답 비율
	avg_response_ms: float  # 평균 응답 시간 (ms)
	usage_by_flow: str  # flow별 토큰 사용량 (마크다운 표)
	cost_krw: float  # 원화 비용 합계
	reports: str  # 보고서 목록 (마크다운 표)
	recent_errors: str  # 최근 에러 로그 (마크다운 표)
