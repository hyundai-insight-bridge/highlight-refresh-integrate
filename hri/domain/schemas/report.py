"""보고서 스키마 · Page, Section, Chunk, Table, Report, ValidationResult, ChartImage, OcrToken, ChartSeries, ChartData (엄정현)

DB에 저장하는 모델(Section·Chunk·Table·Report)의 필드 이름은 sql/schema.sql 컬럼 이름과 같게 둔다.
	- Section → sections / Chunk → chunks / Table → report_tables / Report → reports
	- Page·ValidationResult·ChartImage·OcrToken·ChartSeries·ChartData는 저장하지 않고 업로드(ingest_graph) 중에만 쓴다.
"""

from datetime import date
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

__all__ = [
	"Page",
	"Section",
	"Chunk",
	"Table",
	"Report",
	"ValidationResult",
	"ChartImage",
	"OcrToken",
	"ChartSeries",
	"ChartData",
]

# ---------------------------------------------------------------------
# 1. 쪽 · 섹션
# ---------------------------------------------------------------------
class Page(BaseModel):
	"""PDF 한 쪽. load_pdf()가 만들고 clean_text()·find_body_start()가 다듬는다. (저장 안 함)"""

	page: int = Field(ge=1, description="PDF 기준 쪽 번호, 1부터")
	text: str = Field(default="", description="추출한 글 (머리말·꼬리말 제거 후)")
	is_scanned: bool = Field(default=False, description="글자가 없는 스캔본·빈 쪽이면 True (load_text 노드가 warnings에 기록)")


class Section(BaseModel):
	"""목차 단위 부모 섹션 (sections 테이블 1행). split_sections()가 만든다."""

	report_id: int | None = Field(default=None, description="insert_report() 뒤에 채움")
	section_no: int = Field(ge=0, description="보고서 안 순번, 0부터")
	title: str = Field(description="섹션 제목. 예) 1. 개요")
	start_page: int = Field(ge=1, description="시작 쪽, 1부터")
	end_page: int = Field(ge=1, description="끝 쪽 (start_page 이상인지는 DB CHECK가 확인)")
	text: str = Field(description="섹션 원문 (답변 근거)")


# ---------------------------------------------------------------------
# 2. 청크 · 표
# ---------------------------------------------------------------------
class Chunk(BaseModel):
	"""검색 단위 자식 청크 (chunks 테이블 1행). Chroma id = '{report_id}-{chunk_no}'.

	text 청크: 본문 조각, doc_id = None
	table·chart 청크: text = 캡션+요약, doc_id로 report_tables의 원본 표를 가리킴
	(이 짝이 맞는지는 schema.sql의 ck_chunks_doc_id가 확인한다)
	"""

	report_id: int | None = Field(default=None, description="insert_report() 뒤에 채움")
	chunk_no: int = Field(ge=0, description="보고서 안 순번, 0부터")
	section_no: int = Field(ge=0, description="속한 부모 섹션 순번 (sections FK)")
	page: int = Field(ge=1, description="출처 쪽, 1부터")
	chunk_type: Literal["text", "table", "chart"] = "text"
	category: str | None = Field(default=None, description="분류 (없으면 None)")
	text: str = Field(min_length=1, description="본문, 또는 표·차트의 캡션+요약")
	doc_id: str | None = Field(default=None, description="표·차트 청크만: report_tables.doc_id")


class Table(BaseModel):
	"""보고서 속 표·차트 원본 (report_tables 테이블 1행).

	표: extract_tables()가 만든다. 차트: chart_to_markdown()이 source_type='chart'로 만든다.
	summary(검색용)는 summarize_tables()가 채우고, 답변에는 markdown(원본)을 쓴다.
	confidence는 DB의 ocr_confidence 칸에 저장한다 (insert_tables에서 이름을 바꿔 넣음).
	"""

	doc_id: str = Field(default_factory=lambda: str(uuid4()), description="uuid, report_tables PK")
	report_id: int | None = Field(default=None, description="insert_report() 뒤에 채움")
	page: int = Field(ge=1, description="표·차트가 있는 쪽, 1부터")
	caption: str | None = Field(default=None, description="표 제목. 큰 표를 나누면 '(1/n)'을 붙임")
	rows: list[list[str]] = Field(default_factory=list, description="머리글 행 + 본문 행 (DB에는 저장 안 함)")
	markdown: str = Field(default="", description="table_to_markdown() 결과, 답변용 원본")
	summary: str | None = Field(default=None, description="검색용 1~2문장 요약 (summarize_tables)")
	source_type: Literal["table", "chart"] = "table"
	image_path: str | None = Field(default=None, description="차트만: data/charts/raw/의 PNG 경로")
	confidence: float | None = Field(default=None, ge=0, le=1, description="차트만: match_ratio (validate_chart)")
	needs_review: bool = Field(default=False, description="True면 답변 출처에 '추정값' 표시")


# ---------------------------------------------------------------------
# 3. 보고서 · 검증 결과
# ---------------------------------------------------------------------
class Report(BaseModel):
	"""업로드한 보고서 (reports 테이블 1행). 제목·발행기관·발행일은 extract_report_meta()가 채운다."""

	report_id: int | None = Field(default=None, description="AUTO_INCREMENT, insert_report()가 돌려줌")
	title: str = Field(min_length=1, description="보고서 제목")
	publisher: str = Field(default="현대경제연구원", description="발행기관 (못 찾으면 기본값)")
	published_date: date | None = Field(default=None, description="발행일. '2026-07-31' 글자도 받음, 못 찾으면 None")
	page_count: int = Field(default=0, ge=0, description="PDF 전체 쪽 수")
	chunk_count: int = Field(default=0, ge=0, description="청크 수 (DB 칸 없음, chunks를 집계해서 채움)")
	file_path: str = Field(description="data/raw/에 저장한 PDF 경로")
	uploaded_by: str = Field(description="업로드한 user_id (users FK)")
	file_hash: str | None = Field(
		default=None,
		description="SHA-256 64자. 명세에는 없지만 reports.file_hash가 NOT NULL·UNIQUE라 insert_report() 전에 채워야 함",
	)


class ValidationResult(BaseModel):
	"""validate_pdf() 결과. 예외를 던지지 않고 이 값을 돌려준다."""

	ok: bool = Field(description="통과하면 True")
	reason: str | None = Field(default=None, description="실패 사유 (화면에 그대로 표시). 예) 'PDF 파일만 업로드할 수 있습니다'")


# ---------------------------------------------------------------------
# 4. 차트 (저장 안 함 → chart_to_markdown()이 Table로 바꿔서 저장)
# ---------------------------------------------------------------------
class ChartImage(BaseModel):
	"""extract_charts()가 잘라낸 차트 한 개."""

	page: int = Field(ge=1, description="차트가 있는 쪽, 1부터 (fitz 인덱스+1)")
	caption: str | None = Field(default=None, description="'[그림 n]'·'<그림 n>'·'[차트 n]' 캡션, 못 찾으면 None")
	bbox: list[float] = Field(description="쪽 위 영역 [x0, y0, x1, y1] (pt)")
	image_path: str = Field(description="data/charts/raw/의 PNG 경로 (uuid 파일명)")


class OcrToken(BaseModel):
	"""ocr_chart()가 읽은 글자 한 덩어리 (conf < OCR_MIN_CONF는 버림)."""

	text: str = Field(description="읽은 글자. 숫자는 쉼표·공백·전각 기호를 정리한 값")
	bbox: list[float] = Field(description="이미지 위 영역 [x0, y0, x1, y1] (px). EasyOCR 네 꼭짓점에서 최소·최대로 변환")
	conf: float = Field(ge=0, le=1, description="EasyOCR 신뢰도")
	is_number: bool = Field(default=False, description="숫자 토큰이면 True")


class ChartSeries(BaseModel):
	"""차트의 계열 하나 (범례 한 줄)."""

	name: str = Field(description="계열 이름 (범례에 있는 이름만)")
	values: list[float | None] = Field(description="x축 라벨 순서대로의 값. 못 읽은 칸은 None")


class ChartData(BaseModel):
	"""chart_to_table()이 Vision LLM으로 복원한 차트 데이터 (with_structured_output 대상).

	confidence는 validate_chart()가 match_ratio로 채운다. LLM은 비워 둔다.
	"""

	chart_type: Literal["bar", "line", "pie", "mixed", "other"] = Field(description="차트 유형")
	title: str = Field(default="", description="차트 제목")
	unit: str = Field(default="", description="단위. 예) %, 조 원")
	x_labels: list[str] = Field(description="x축 라벨 (표의 행이 됨)")
	series: list[ChartSeries] = Field(description="계열 목록 (표의 열이 됨)")
	needs_review: bool = Field(default=False, description="눈금으로 읽은 근사값이 있거나 검수에 실패하면 True")
	confidence: float | None = Field(default=None, ge=0, le=1, description="LLM 숫자 중 OCR 토큰에 있는 비율")

