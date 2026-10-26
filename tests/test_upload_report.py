"""upload_report() 단독 테스트 (실제 PDF·DB·Chroma·OpenAI 없이 실행, 비용 0원)

- 진짜 업로드 그래프 대신 '정해진 순서로 노드 결과를 내보내는 가짜 그래프'를 끼워 넣는다.
- 가짜 그래프 안에서 가짜 채팅 모델을 호출해 토큰 사용량(UsageMetadataCallbackHandler)도 흉내 낸다.
- insert_usage(), cost_korean_won()은 호출 기록만 남기는 가짜로 바꾼다.

실행: poetry run pytest tests/test_upload_report.py -v
"""
import importlib
import sys
import types

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

MODULE = "hri.service.document_service"


# ─────────────────────────────────────────────────────────────
# 가짜 부품
# ─────────────────────────────────────────────────────────────
def fake_llm_call(config: dict, input_tokens: int = 100, output_tokens: int = 20) -> None:
    """그래프 노드 안에서 AI를 한 번 부른 것처럼 사용량을 남긴다."""
    msg = AIMessage(content="요약", response_metadata={"model_name": "gpt-4o-mini"},
                    usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens,
                                    "total_tokens": input_tokens + output_tokens})
    GenericFakeChatModel(messages=iter([msg])).invoke("x", config=config)


class FakeGraph:
    """graph.stream(..., stream_mode="updates")를 흉내 낸다.

    steps: [("노드이름", {바뀐 상태}), ...] 순서대로 내보냄
    llm_at: 이 노드를 내보내기 전에 가짜 AI 호출 (사용량 발생)
    raise_at: 이 노드에서 예외 발생
    """

    def __init__(self, steps, llm_at=(), raise_at=None):
        self.steps, self.llm_at, self.raise_at = steps, set(llm_at), raise_at
        self.calls = []

    def stream(self, inputs, stream_mode=None, config=None):
        self.calls.append({"inputs": inputs, "stream_mode": stream_mode, "config": config})
        for node, state in self.steps:
            if node in self.llm_at:
                fake_llm_call(config or {})
            if node == self.raise_at:
                raise RuntimeError(f"{node} 노드 실패")
            yield {node: state}


SUCCESS_STEPS = [
    ("validate", {"ok": True}),
    ("load_text", {}),
    ("extract_tables", {}),
    ("process_charts", {}),
    ("split", {}),
    ("summarize_tables", {}),
    ("persist", {"report_id": 12, "counts": {"text": 157, "table": 8, "chart": 3},
                 "warnings": ["p.14 차트 수치 검토 필요"]}),
]

VALIDATE_FAIL_STEPS = [("validate", {"ok": False, "reason": "PDF가 아닙니다"})]


@pytest.fixture
def env(monkeypatch):
    """document_service가 import하는 3개 모듈을 가짜로 바꾸고, 새로 import한 모듈을 돌려준다."""
    state = {"graph": None, "usage_calls": []}

    registry = types.ModuleType("hri.graph.registry")
    registry.get_ingest_graph = lambda: state["graph"]

    metrics = types.ModuleType("hri.util.metrics")
    metrics.cost_korean_won = lambda usage, *a, **k: 1.23

    usage_dao = types.ModuleType("hri.dao.usage_dao")
    usage_dao.insert_usage = lambda **kw: state["usage_calls"].append(kw)

    for name, mod in [("hri.graph.registry", registry), ("hri.util.metrics", metrics),
                      ("hri.dao.usage_dao", usage_dao)]:
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, MODULE, raising=False)

    state["module"] = importlib.import_module(MODULE)
    return state


def run(env, graph):
    env["graph"] = graph
    return list(env["module"].upload_report("sample.pdf", "user01"))


# ─────────────────────────────────────────────────────────────
# 1. 정상 업로드
# ─────────────────────────────────────────────────────────────
def test_그래프에_입력과_설정을_올바르게_넘김(env):
    graph = FakeGraph(SUCCESS_STEPS)
    run(env, graph)
    call = graph.calls[0]
    assert call["inputs"] == {"file_path": "sample.pdf", "user_id": "user01"}
    assert call["stream_mode"] == "updates"
    assert call["config"]["callbacks"], "사용량 콜백이 config에 들어가야 합니다"


def test_노드마다_진행상황을_내보냄(env):
    out = run(env, FakeGraph(SUCCESS_STEPS))
    steps = [m["step"] for m in out if "step" in m]
    assert steps == [name for name, _ in SUCCESS_STEPS]


def test_마지막_항목에_결과가_있음(env):
    last = run(env, FakeGraph(SUCCESS_STEPS))[-1]
    assert last["report_id"] == 12
    assert last["counts"] == {"text": 157, "table": 8, "chart": 3}
    assert last["warnings"] == ["p.14 차트 수치 검토 필요"]


def test_성공하면_사용량을_한번_기록(env):
    run(env, FakeGraph(SUCCESS_STEPS, llm_at=["summarize_tables", "process_charts"]))
    assert len(env["usage_calls"]) == 1
    call = env["usage_calls"][0]
    assert call["flow"] == "ingest" and call["ref_id"] == 12
    assert call["usage"]["gpt-4o-mini"]["input_tokens"] == 200      # 100 + 100 (2번 호출 합계)
    assert call["cost_krw"] == 1.23


# ─────────────────────────────────────────────────────────────
# 2. 실패 상황 (지금 뼈대 코드에서 실패하는 테스트 = 고쳐야 할 점)
# ─────────────────────────────────────────────────────────────
def test_검증_실패해도_에러없이_끝나고_결과를_알림(env):
    out = run(env, FakeGraph(VALIDATE_FAIL_STEPS))          # 예외가 밖으로 나오면 실패
    assert out, "아무것도 내보내지 않았습니다"
    assert "report_id" not in out[-1], "실패인데 report_id가 있습니다"


def test_중간_노드_예외도_에러없이_끝나고_결과를_알림(env):
    out = run(env, FakeGraph(SUCCESS_STEPS, raise_at="split"))
    assert out and "report_id" not in out[-1]


def test_실패해도_쓴_AI_비용은_기록(env):
    run(env, FakeGraph(SUCCESS_STEPS, llm_at=["process_charts"], raise_at="split"))
    assert len(env["usage_calls"]) == 1, "AI를 썼는데 비용이 기록되지 않았습니다"
    assert env["usage_calls"][0]["ref_id"] is None


def test_AI를_안_썼으면_기록하지_않음_또는_0원(env):
    run(env, FakeGraph(VALIDATE_FAIL_STEPS))
    assert all(c.get("usage") for c in env["usage_calls"]), "빈 사용량을 기록했습니다"
