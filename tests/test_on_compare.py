"""on_compare 로직 테스트 · 가짜 비교표·차트 사용 (장유빈)"""
import gradio as gr
import pytest

from hri.view import indicator_view
from hri.view.indicator_view import (
	COMPARE_ERROR_MESSAGE,
	NEED_MORE_REPORTS_MESSAGE,
	NO_CHART_NOTE,
	NO_INDICATORS_MESSAGE,
	on_compare,
)


def _use(monkeypatch, table="| 표 |", image="data/plots/compare_x.png"):
	"""build_compare_table·plot_indicators를 가짜로 바꾸고 받은 인자를 기록해 돌려준다."""
	calls = {"table": [], "plot": []}

	def fake_table(ids):
		calls["table"].append(ids)
		return table

	def fake_plot(ids):
		calls["plot"].append(ids)
		return image

	monkeypatch.setattr(indicator_view, "build_compare_table", fake_table)
	monkeypatch.setattr(indicator_view, "plot_indicators", fake_plot)
	return calls


@pytest.mark.parametrize("ids", [None, [], [1], ["1"], [2, 2]])
def test_fewer_than_two_reports_shows_message(monkeypatch, ids):
	calls = _use(monkeypatch)
	assert on_compare(ids) == (NEED_MORE_REPORTS_MESSAGE, None)
	assert calls == {"table": [], "plot": []}


def test_two_reports_return_table_and_image(monkeypatch):
	calls = _use(monkeypatch)
	assert on_compare([1, 2]) == ("| 표 |", "data/plots/compare_x.png")
	assert calls == {"table": [[1, 2]], "plot": [[1, 2]]}


def test_ids_are_converted_to_int(monkeypatch):
	calls = _use(monkeypatch)
	on_compare(["3", 4.0])
	assert calls["table"] == [[3, 4]]


def test_no_indicators_skips_chart(monkeypatch):
	calls = _use(monkeypatch, table="")
	assert on_compare([1, 2]) == (NO_INDICATORS_MESSAGE, None)
	assert calls["plot"] == []


def test_no_chart_adds_note_under_table(monkeypatch):
	_use(monkeypatch, image=None)
	assert on_compare([1, 2]) == (f"| 표 |\n\n{NO_CHART_NOTE}", None)


@pytest.mark.parametrize("target", ["build_compare_table", "plot_indicators"])
def test_error_shows_message(monkeypatch, target):
	_use(monkeypatch)

	def boom(ids):
		raise RuntimeError("실패")

	monkeypatch.setattr(indicator_view, target, boom)
	assert on_compare([1, 2]) == (COMPARE_ERROR_MESSAGE, None)


def test_progress_is_reported(monkeypatch):
	_use(monkeypatch)
	seen = []
	on_compare([1, 2], progress=lambda fraction, desc=None: seen.append((fraction, desc)))
	assert [f for f, _ in seen] == [0.1, 0.7]


def test_works_as_gradio_event_handler(monkeypatch):
	_use(monkeypatch)
	with gr.Blocks():
		dropdown = gr.Dropdown(choices=[("A", 1), ("B", 2)], multiselect=True)
		button = gr.Button()
		table, image = gr.Markdown(), gr.Image()
		button.click(on_compare, inputs=dropdown, outputs=[table, image])