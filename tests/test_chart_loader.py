"""extract_charts()가 명세대로 동작하는지 확인하는 테스트 (네트워크·DB·.env 없이 실행).

테스트용 PDF는 pymupdf로 직접 그려 tmp_path(pytest가 주는 임시 폴더)에 만든다.
- 래스터 차트: 색칠한 PNG 그림을 insert_image로 넣는다 (HRI 차트는 대부분 204×160pt 그림)
- 벡터 차트: 축 2개 + 꺾은선을 선으로 그린다 (LG경영연구원 보고서 차트 모양)
- 표: 격자 선 + 칸 글자 / 글상자: 테두리 + 글 여러 줄 (HRI 요약 쪽·연구진 상자 모양)
작업 폴더를 tmp_path로 바꿔(monkeypatch.chdir) PNG가 저장소의 data/charts/raw/에 쌓이지 않게 한다.
"""

from pathlib import Path

import pymupdf
import pytest

import hri.loader.chart_loader as chart_loader
from hri.domain.schemas import ChartImage, Settings
from hri.graph.ingest_graph import extract_charts_node
from hri.loader.chart_loader import extract_charts


# load_settings()는 .env의 MySQL 값이 없으면 오류를 내므로, 테스트에서는 가짜 설정으로 바꿔 끼운다
def fake_settings(chart_dpi=200, min_chart_pt=120):
	return Settings(
		mysql_host="localhost",
		mysql_user="test",
		mysql_password="test",
		mysql_database="test",
		chart_dpi=chart_dpi,
		min_chart_pt=min_chart_pt,
	)


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
	monkeypatch.setattr(chart_loader, "load_settings", lambda: fake_settings())
	monkeypatch.chdir(tmp_path)


# 색칠한 PNG 그림 (bytes). 넣을 때 keep_proportion=False로 영역 크기에 딱 맞춘다
def png_bytes(color=(200, 0, 0)):
	pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40), False)
	pix.set_rect(pix.irect, color)
	return pix.tobytes("png")


def new_pdf(page_count=1):
	doc = pymupdf.open()
	for _ in range(page_count):
		doc.new_page(width=595, height=842)
	return doc


def save(doc, path):
	doc.save(str(path))
	doc.close()
	return str(path)


# 글 한 줄 (fontname="korea": pymupdf에 들어 있는 한글 글꼴)
def write(page, x, y, text, size=9):
	page.insert_text((x, y), text, fontname="korea", fontsize=size)


# HRI 캡션 '< 제목 >': 실제 PDF처럼 꺾쇠는 다른 글꼴(helv 11pt)로 한 줄 안에 이어 쓴다
# → 꺾쇠의 y 좌표가 제목보다 2~3pt 위에 온다 (HRI 부동산 17쪽: '<' y0=544.9, 제목 y0=546.5)
# 글꼴이 다른 글을 한 줄로 쓰려고 TextWriter를 쓴다 (insert_text를 따로 부르면 다른 줄로 읽힘)
def write_hri_caption(page, x, y, title):
	writer = pymupdf.TextWriter(page.rect)
	helv, korea = pymupdf.Font("helv"), pymupdf.Font("korea")
	_, end = writer.append((x, y), "<", font=helv, fontsize=11)
	_, end = writer.append(end, f" {title} ", font=korea, fontsize=9)
	writer.append(end, ">", font=helv, fontsize=11)
	writer.write_text(page)


# 꺾은선 벡터 차트: 왼쪽 위 (x, y), 크기 w×h
def draw_line_chart(page, x, y, w, h):
	page.draw_line((x, y), (x, y + h))
	page.draw_line((x, y + h), (x + w, y + h))
	points = [(x + w * i / 5, y + h * (0.8 - 0.12 * i)) for i in range(6)]
	page.draw_polyline(points, color=(0, 0, 1))
	write(page, x + 5, y + h - 5, "0")
	write(page, x + w - 20, y + 15, "2.4%")


# 격자 표: 왼쪽 위 (x, y), rows×cols 칸, 칸 크기 cw×ch
def draw_table(page, x, y, rows, cols, cw=60, ch=25):
	for r in range(rows + 1):
		page.draw_line((x, y + r * ch), (x + cols * cw, y + r * ch))
	for c in range(cols + 1):
		page.draw_line((x + c * cw, y), (x + c * cw, y + rows * ch))
	for r in range(rows):
		for c in range(cols):
			write(page, x + c * cw + 5, y + r * ch + 16, f"{r}.{c}")


# 글상자: 테두리 + 글 lines줄 (HRI 요약 쪽 · 연구진 상자 모양)
def draw_text_box(page, rect, lines):
	page.draw_rect(rect)
	for i in range(lines):
		write(page, rect.x0 + 5, rect.y0 + 14 + i * 13, "현대경제연구원은 물가 흐름을 점검하고 시사점을 제시하고자 함", size=11)


# ---------------------------------------------------------------------
# 래스터 차트
# ---------------------------------------------------------------------
# [확인 1] 그림 차트 1개 → ChartImage 1개. page는 인덱스+1, bbox는 그림 위치, PNG는 data/charts/raw/{uuid}.png
def test_raster_chart(tmp_path):
	doc = new_pdf(2)
	rect = pymupdf.Rect(90, 500, 294, 660)
	doc[1].insert_image(rect, stream=png_bytes(), keep_proportion=False)
	charts = extract_charts(save(doc, tmp_path / "a.pdf"))

	assert len(charts) == 1
	chart = charts[0]
	assert isinstance(chart, ChartImage)
	assert chart.page == 2
	assert [round(v) for v in chart.bbox] == [90, 500, 294, 660]
	path = Path(chart.image_path)
	assert path.parent.as_posix() == "data/charts/raw"
	assert path.suffix == ".png" and len(path.stem) == 36  # uuid4 문자열 길이
	assert (tmp_path / path).exists()


# [확인 2] CHART_DPI(200)로 자른다: 204pt × 200/72 ≈ 567px
def test_png_size_follows_chart_dpi(tmp_path):
	doc = new_pdf()
	doc[0].insert_image(pymupdf.Rect(90, 500, 294, 660), stream=png_bytes(), keep_proportion=False)
	chart = extract_charts(save(doc, tmp_path / "a.pdf"))[0]

	pix = pymupdf.Pixmap(chart.image_path)
	assert abs(pix.width - 204 * 200 / 72) <= 2
	assert abs(pix.height - 160 * 200 / 72) <= 2


# [확인 3] 가로·세로 MIN_CHART_PT(120pt) 미만은 뺀다 (120pt 딱 맞으면 남긴다)
@pytest.mark.parametrize(
	"width, height, expected",
	[(120, 120, 1), (119, 200, 0), (200, 119, 0), (80, 11, 0)],
)
def test_min_chart_pt(tmp_path, width, height, expected):
	doc = new_pdf()
	doc[0].insert_image(pymupdf.Rect(100, 300, 100 + width, 300 + height), stream=png_bytes(), keep_proportion=False)
	assert len(extract_charts(save(doc, tmp_path / "a.pdf"))) == expected


# [확인 4] 같은 xref 그림이 3쪽 이상 나오면 로고로 보고 뺀다 (2쪽까지는 차트로 남긴다)
@pytest.mark.parametrize("page_count, expected", [(2, 2), (3, 0)])
def test_logo_repeated_xref(tmp_path, page_count, expected):
	doc = new_pdf(page_count)
	rect = pymupdf.Rect(100, 300, 300, 460)
	xref = doc[0].insert_image(rect, stream=png_bytes(), keep_proportion=False)
	for page in list(doc)[1:]:
		page.insert_image(rect, xref=xref)  # 같은 그림을 다시 씀 (xref 같음)
	assert len(extract_charts(save(doc, tmp_path / "a.pdf"))) == expected


# [확인 5] 쪽 전체를 덮는 그림(HRI 표지 배경)은 뺀다
def test_full_page_image_excluded(tmp_path):
	doc = new_pdf()
	doc[0].insert_image(doc[0].rect, stream=png_bytes(), keep_proportion=False)
	assert extract_charts(save(doc, tmp_path / "a.pdf")) == []


# [확인 6] 같은 그림을 한 쪽에 두 번 넣어도 위치마다 1개씩 (같은 xref가 get_images()에 두 번 나와도 중복 없음)
def test_same_image_twice_on_page(tmp_path):
	doc = new_pdf()
	image = png_bytes()
	doc[0].insert_image(pymupdf.Rect(90, 100, 294, 260), stream=image, keep_proportion=False)
	doc[0].insert_image(pymupdf.Rect(90, 400, 294, 560), stream=image, keep_proportion=False)
	charts = extract_charts(save(doc, tmp_path / "a.pdf"))

	assert [round(chart.bbox[1]) for chart in charts] == [100, 400]


# ---------------------------------------------------------------------
# 벡터 차트
# ---------------------------------------------------------------------
# [확인 7] 선으로 그린 차트 → cluster_drawings() 영역으로 잡는다
def test_vector_chart(tmp_path):
	doc = new_pdf()
	draw_line_chart(doc[0], 300, 400, 200, 150)
	charts = extract_charts(save(doc, tmp_path / "a.pdf"))

	assert len(charts) == 1
	x0, y0, x1, y1 = charts[0].bbox
	assert x0 <= 300 and y0 <= 400 and x1 >= 500 and y1 >= 550
	assert Path(charts[0].image_path).exists()


# [확인 8] 작은 벡터 도형(120pt 미만)은 뺀다
def test_small_vector_excluded(tmp_path):
	doc = new_pdf()
	draw_line_chart(doc[0], 300, 400, 100, 150)
	assert extract_charts(save(doc, tmp_path / "a.pdf")) == []


# [확인 9] 선으로 그린 표는 뺀다 (표는 extract_tables 몫)
def test_vector_table_excluded(tmp_path):
	doc = new_pdf()
	draw_table(doc[0], 100, 300, rows=6, cols=4)
	assert extract_charts(save(doc, tmp_path / "a.pdf")) == []


# [확인 10] 글상자(테두리 + 글이 가득한 상자)는 뺀다
def test_text_box_excluded(tmp_path):
	doc = new_pdf()
	draw_text_box(doc[0], pymupdf.Rect(86, 300, 509, 450), lines=10)
	assert extract_charts(save(doc, tmp_path / "a.pdf")) == []


# [확인 11] 그림 차트를 감싼 상자 → 그림 쪽 1개만 (같은 차트를 두 번 자르지 않음)
def test_box_around_raster_chart(tmp_path):
	doc = new_pdf()
	page = doc[0]
	page.draw_rect(pymupdf.Rect(86, 300, 509, 520))
	page.insert_image(pymupdf.Rect(100, 330, 300, 500), stream=png_bytes(), keep_proportion=False)
	charts = extract_charts(save(doc, tmp_path / "a.pdf"))

	assert len(charts) == 1
	assert [round(v) for v in charts[0].bbox] == [100, 330, 300, 500]


# ---------------------------------------------------------------------
# 캡션
# ---------------------------------------------------------------------
# [확인 12] HRI '< 제목 >': 나란히 놓인 두 차트가 각자 위의 캡션을 갖는다. 아래 '자료 :' 줄은 캡션이 아님
def test_hri_captions_side_by_side(tmp_path):
	doc = new_pdf()
	page = doc[0]
	write_hri_caption(page, 110, 490, "소비자물가 상승률")
	write_hri_caption(page, 320, 490, "원/달러 환율 추이")
	page.insert_image(pymupdf.Rect(90, 500, 294, 660), stream=png_bytes(), keep_proportion=False)
	page.insert_image(pymupdf.Rect(303, 500, 507, 660), stream=png_bytes((0, 0, 200)), keep_proportion=False)
	write(page, 92, 675, "자료 : 통계청.")
	charts = extract_charts(save(doc, tmp_path / "a.pdf"))

	assert [chart.caption for chart in charts] == ["< 소비자물가 상승률 >", "< 원/달러 환율 추이 >"]


# [확인 13] 두 줄로 나뉜 캡션은 이어 붙인다
def test_two_line_caption(tmp_path):
	doc = new_pdf()
	page = doc[0]
	write(page, 100, 470, "< 한국의 민간신용(GDP대비)")
	write(page, 100, 485, "비율 추이 >")
	page.insert_image(pymupdf.Rect(90, 500, 294, 660), stream=png_bytes(), keep_proportion=False)
	chart = extract_charts(save(doc, tmp_path / "a.pdf"))[0]

	assert chart.caption == "< 한국의 민간신용(GDP대비) 비율 추이 >"


# [확인 14] 차트보다 넓은 캡션: 앞의 '<'가 차트 왼쪽 밖에 있어도 빠지지 않는다 (HRI 트럼프 노믹스 26쪽 모양)
def test_caption_wider_than_chart(tmp_path):
	doc = new_pdf()
	page = doc[0]
	write(page, 297, 490, "< 대중 수입 관세율 추이 >")  # "<"(297~306pt)의 가운데가 차트 왼쪽(303pt) 밖
	page.insert_image(pymupdf.Rect(303, 500, 507, 660), stream=png_bytes(), keep_proportion=False)
	chart = extract_charts(save(doc, tmp_path / "a.pdf"))[0]

	assert chart.caption == "< 대중 수입 관세율 추이 >"


# [확인 15] 위에 없으면 아래에서 찾는다: '[그림 n] 제목', '<그림 n>'
@pytest.mark.parametrize("text", ["[그림 2-1] 채권 종류별 발행 잔액", "<그림 3>"])
def test_caption_below(tmp_path, text):
	doc = new_pdf()
	page = doc[0]
	page.insert_image(pymupdf.Rect(90, 500, 294, 660), stream=png_bytes(), keep_proportion=False)
	write(page, 100, 680, text)
	chart = extract_charts(save(doc, tmp_path / "a.pdf"))[0]

	assert chart.caption == text


# [확인 16] 아래 캡션 다음 줄의 '자료 :'·'단위' 줄은 캡션에 붙이지 않는다
def test_caption_below_stops_at_line_end(tmp_path):
	doc = new_pdf()
	page = doc[0]
	page.insert_image(pymupdf.Rect(90, 300, 294, 460), stream=png_bytes(), keep_proportion=False)
	write(page, 100, 475, "[그림 1] 소비자물가 추이")
	write(page, 100, 490, "자료 : 통계청, 단위 : %")
	chart = extract_charts(save(doc, tmp_path / "a.pdf"))[0]

	assert chart.caption == "[그림 1] 소비자물가 추이"


# [확인 17] 캡션 모양이 아니거나(출처 줄·빈 꺾쇠) 40pt보다 멀면 None
@pytest.mark.parametrize(
	"text, y", [("자료 : 한국은행.", 490), ("< >", 490), ("< 소비자물가 상승률 >", 450)]
)
def test_no_caption(tmp_path, text, y):
	doc = new_pdf()
	write(doc[0], 100, y, text)
	doc[0].insert_image(pymupdf.Rect(90, 500, 294, 660), stream=png_bytes(), keep_proportion=False)
	assert extract_charts(save(doc, tmp_path / "a.pdf"))[0].caption is None


# ---------------------------------------------------------------------
# 순서 · 설정 · 노드 연결
# ---------------------------------------------------------------------
# [확인 18] 쪽 순서, 쪽 안에서는 위 → 아래 (래스터·벡터가 섞여도)
def test_order(tmp_path):
	doc = new_pdf(2)
	doc[1].insert_image(pymupdf.Rect(90, 100, 294, 260), stream=png_bytes(), keep_proportion=False)
	doc[0].insert_image(pymupdf.Rect(90, 500, 294, 660), stream=png_bytes((0, 200, 0)), keep_proportion=False)
	draw_line_chart(doc[0], 300, 100, 200, 150)  # 1쪽: 그림(아래)을 먼저 넣고 벡터 차트(위)를 나중에 그림
	charts = extract_charts(save(doc, tmp_path / "a.pdf"))

	assert [(chart.page, round(chart.bbox[1])) for chart in charts] == [(1, 100), (1, 500), (2, 100)]


# [확인 19] CHART_DPI·MIN_CHART_PT는 Settings에서 읽는다
def test_settings_used(tmp_path, monkeypatch):
	monkeypatch.setattr(chart_loader, "load_settings", lambda: fake_settings(chart_dpi=100, min_chart_pt=170))
	doc = new_pdf()
	doc[0].insert_image(pymupdf.Rect(90, 100, 294, 260), stream=png_bytes(), keep_proportion=False)  # 204×160 → 170 미만이라 빠짐
	doc[0].insert_image(pymupdf.Rect(90, 400, 290, 580), stream=png_bytes(), keep_proportion=False)  # 200×180
	charts = extract_charts(save(doc, tmp_path / "a.pdf"))

	assert len(charts) == 1
	assert abs(pymupdf.Pixmap(charts[0].image_path).width - 200 * 100 / 72) <= 2


# [확인 20] 차트가 없으면 빈 목록, 폴더·PNG도 만들지 않는다
def test_no_chart(tmp_path):
	doc = new_pdf()
	write(doc[0], 72, 72, "본문만 있는 쪽")
	assert extract_charts(save(doc, tmp_path / "a.pdf")) == []
	assert not (tmp_path / "data/charts/raw").exists()


# [확인 21] extract_charts_node가 진짜 extract_charts를 불러 {'charts': [...]}로 돌려준다 (3.8.2 노드와 연결)
def test_extract_charts_node(tmp_path):
	doc = new_pdf()
	doc[0].insert_image(pymupdf.Rect(90, 500, 294, 660), stream=png_bytes(), keep_proportion=False)
	result = extract_charts_node({"file_path": save(doc, tmp_path / "a.pdf")})

	assert list(result) == ["charts"]
	assert len(result["charts"]) == 1 and result["charts"][0].page == 1
