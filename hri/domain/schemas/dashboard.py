"""대시보드 스키마 · DashboardData (임세준)"""

from pydantic import BaseModel

__all__ = ["DashboardData"]


class DashboardData(BaseModel):
	"""
	관리자 대시보드에 보여줄 데이터

	top_questions: 질문 TOP 10 (마크다운 표)
	source_ratio: 자료 유무 응답 비율
	avg_response_ms: 평균 응답 시간 (ms)
	usage_by_flow: flow별 토큰 사용량 (마크다운 표)
	cost_krw: 원화 비용 합계
	reports: 보고서 목록 (마크다운 표)
	recent_errors: 최근 에러 로그 (마크다운 표)
	"""

	top_questions: str  
	source_ratio: float  
	avg_response_ms: float  
	usage_by_flow: str  
	cost_krw: float  
	reports: str  
	recent_errors: str  
