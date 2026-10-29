"""
외부 API 장애·빈 결과 테스트 (서동안, WBS 4.1.6)
환율 API(한국수출입은행·ECOS)가 실패하거나 빈 결과를 줄 때 서비스가 멈추지 않고
① 토큰 비용 환율은 수출입은행 → ECOS → 기본 환율 1,400원 순서로 넘어가는지(get_usd_krw)
② 통화별 환율은 실패·빈 결과인 통화만 빠지고 나머지는 나오는지(get_exchange_rates)
③ 오류 메시지에 API 키가 들어가지 않는지, ④ ECOS 통계용어가 빈 결과면 None·오류면 예외인지 확인한다. 네트워크 없이 가짜 응답으로 실행한다.

기존 tests/test_exchange_client.py(정상·전날 거슬러 가기·오류 코드), tests/test_term_service.py·test_chat_view_term.py
(용어 풀이 오류 → ExternalApiError → 화면 문구)와 겹치지 않게 장애 상황만 본다.
"""

import importlib
import sys

import httpx
import pytest
from ecos.exceptions import EcosResponseError
from ecos.models import StatisticRow

from hri.api import ecos_client, exchange_client
from hri.domain.schemas.external import EcosExchangeRate

SECRET_KEY = "SECRET-AUTH-KEY-123"


# ---------------------------------------------------------------------
# 공통: llm_client는 import할 때 .env를 읽으므로 가짜 값을 넣고 새로 불러온다
# ---------------------------------------------------------------------
@pytest.fixture
def llm_client(monkeypatch):
	for name, value in {"MYSQL_HOST": "x", "MYSQL_USER": "x", "MYSQL_PASSWORD": "x", "MYSQL_DATABASE": "x",
			"CHROMA_MODE": "http", "CHROMA_HOST": "x", "OPENAI_API_KEY": "sk-test", "KOREAEXIM_API_KEY": SECRET_KEY}.items():
		monkeypatch.setenv(name, value)
	monkeypatch.delitem(sys.modules, "hri.llm.llm_client", raising=False)
	module = importlib.import_module("hri.llm.llm_client")
	yield module
	sys.modules.pop("hri.llm.llm_client", None)


def _fail(error):
	def raiser(*args, **kwargs):
		raise error
	return raiser


# =====================================================================
# 1. 토큰 비용 환율 get_usd_krw(): 수출입은행 → ECOS → 1,400원
# =====================================================================

# [확인 1] 수출입은행이 되면 그 값을 쓰고 ECOS는 부르지 않는다
def test_usd_krw_uses_exim_first(llm_client, monkeypatch):
	monkeypatch.setattr(exchange_client, "get_exchange_rate", lambda key, cur="USD": 1385.5)
	monkeypatch.setattr(ecos_client, "get_exchange_rates", _fail(AssertionError("ECOS를 부르면 안 됨")))
	assert llm_client.get_usd_krw() == 1385.5


# [확인 2] 수출입은행·ECOS가 모두 실패하면 기본 환율 1,400원 (서비스는 멈추지 않음)
@pytest.mark.parametrize("exim_error", [
	RuntimeError("수출입은행 API HTTP 오류: 500"),
	RuntimeError("수출입은행 API 오류 코드: 3"),       # 인증키 오류
	RuntimeError("수출입은행 API 오류 코드: 4"),       # 일일 제한 횟수 초과
	LookupError("최근 7일간 USD 환율을 찾지 못했습니다"),  # 빈 결과
	httpx.ConnectTimeout("timed out"),                 # 네트워크 장애
], ids=["HTTP500", "인증키오류", "일일제한", "빈결과", "타임아웃"])
def test_usd_krw_default_when_all_fail(llm_client, monkeypatch, exim_error):
	monkeypatch.setattr(exchange_client, "get_exchange_rate", _fail(exim_error))
	monkeypatch.setattr(ecos_client, "get_exchange_rates", _fail(EcosResponseError("ERROR-100", "인증키가 유효하지 않습니다")))
	assert llm_client.get_usd_krw() == llm_client.DEFAULT_USD_KRW == 1400.0


# [확인 3] 환율을 못 가져와도 원화 비용은 1,400원으로 계산된다 (기록이 0원·오류로 남지 않음)
def test_cost_uses_default_rate(llm_client, monkeypatch):
	monkeypatch.setattr(exchange_client, "get_exchange_rate", _fail(httpx.ConnectTimeout("timed out")))
	monkeypatch.setattr(ecos_client, "get_exchange_rates", _fail(EcosResponseError("ERROR-100", "x")))
	monkeypatch.setattr(llm_client, "load_settings", lambda: type("S", (), {
		"model_prices": '{"gpt-5-mini": {"input": 0.25, "output": 2.00}}', "koreaexim_api_key": SECRET_KEY})())
	usage = {"gpt-5-mini-2025-08-07": {"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000}}
	assert llm_client.cost_korean_won(usage, llm_client.get_usd_krw()) == 0.25 * 1400.0


# [확인 4] 수출입은행만 실패하면 ECOS 원/달러 환율을 쓴다 (명세서: 수출입은행 → ECOS → 1,400원)
def test_usd_krw_falls_back_to_ecos(llm_client, monkeypatch):
	monkeypatch.setattr(exchange_client, "get_exchange_rate", _fail(RuntimeError("수출입은행 API HTTP 오류: 500")))
	monkeypatch.setattr(ecos_client, "get_exchange_rates",
		lambda currencies=None, **kw: [EcosExchangeRate(currency="USD", value=1350.0, base_date="20261028")])
	assert llm_client.get_usd_krw() == 1350.0


# [확인 4-2] 수출입은행이 실패하고 ECOS도 빈 결과(최근 영업일 값 없음)면 1,400원
def test_usd_krw_default_when_ecos_empty(llm_client, monkeypatch):
	monkeypatch.setattr(exchange_client, "get_exchange_rate", _fail(LookupError("최근 7일간 USD 환율을 찾지 못했습니다")))
	monkeypatch.setattr(ecos_client, "get_exchange_rates", lambda currencies=None, **kw: [])
	assert llm_client.get_usd_krw() == 1400.0


# =====================================================================
# 2. 수출입은행 클라이언트: 오류 메시지에 API 키가 없어야 함
# =====================================================================

@pytest.fixture
def exim_server(monkeypatch):
	"""수출입은행 서버 대신 responses에 넣은 응답(또는 예외)을 차례로 돌려준다."""
	responses = []
	real_client = httpx.Client

	def handler(request):
		item = responses.pop(0)
		if isinstance(item, Exception):
			raise item
		return item

	monkeypatch.setattr(exchange_client.httpx, "Client",
		lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
	return responses


# [확인 5] HTTP 오류·오류 코드·빈 결과 모두 예외 메시지에 API 키가 들어가지 않는다
@pytest.mark.parametrize("bodies", [
	[httpx.Response(500, text="server error")],
	[httpx.Response(200, json=[{"result": 3}])],
	[httpx.Response(200, json=[])] * 3,
], ids=["HTTP500", "인증키오류", "빈결과"])
def test_exim_error_message_has_no_key(exim_server, bodies):
	exim_server.extend(bodies)
	with pytest.raises(Exception) as exc:
		exchange_client.get_exchange_rate(SECRET_KEY, "USD", max_back_days=2)
	assert SECRET_KEY not in str(exc.value)


# [확인 6] 네트워크 타임아웃은 그대로 예외로 올라온다 (get_usd_krw가 받아 다음 단계로 넘어감)
def test_exim_timeout_raises(exim_server):
	exim_server.append(httpx.ReadTimeout("timed out"))
	with pytest.raises(httpx.TimeoutException):
		exchange_client.get_exchange_rate(SECRET_KEY)


# =====================================================================
# 3. ECOS 통화별 환율 get_exchange_rates(): 실패·빈 결과인 통화만 빠진다
# =====================================================================

def _row(day: str, value: str) -> StatisticRow:
	return StatisticRow(stat_code="731Y001", stat_name="환율", item_code1="", item_name1="", item_code2="", item_name2="",
		item_code3="", item_name3="", item_code4="", item_name4="", unit_name="원", wgt="", time=day, data_value=value)


class FakeEcos:
	"""통화(항목코드)별로 정해 둔 결과를 돌려주는 가짜 ECOS 클라이언트. 값이 예외면 그 예외를 낸다."""

	def __init__(self, by_currency: dict):
		codes = {code: cur for cur, code in ecos_client.CURRENCY_ITEM_CODES.items()}
		self.by_code = {code: by_currency[cur] for code, cur in codes.items() if cur in by_currency}

	def search(self, stat_code, cycle, start, end, item_code1=None, **kwargs):
		result = self.by_code[item_code1]
		if isinstance(result, Exception):
			raise result
		return result


NO_DATA = EcosResponseError("INFO-200", "해당하는 데이터가 없습니다.")


# [확인 7] 정상: 기간 안에서 가장 최근 영업일 값을 고른다
def test_rates_pick_latest_day():
	client = FakeEcos({"USD": [_row("20261027", "1,380.1"), _row("20261028", "1,385.5")]})
	rates = ecos_client.get_exchange_rates(["USD"], client=client)
	assert [(r.currency, r.value, r.base_date) for r in rates] == [("USD", 1385.5, "20261028")]


# [확인 8] 한 통화만 데이터가 없으면(INFO-200) 그 통화만 빠지고 나머지는 나온다
def test_rates_skip_currency_without_data():
	client = FakeEcos({"USD": [_row("20261028", "1385.5")], "JPY": NO_DATA, "EUR": [_row("20261028", "1490.2")]})
	rates = ecos_client.get_exchange_rates(client=client)
	assert [r.currency for r in rates] == ["USD", "EUR"]


# [확인 9] 값이 비었거나 숫자가 아닌 행('-', '')은 건너뛰고, 남는 행이 없으면 그 통화는 빠진다
def test_rates_skip_invalid_values():
	client = FakeEcos({"USD": [_row("20261027", "1380.0"), _row("20261028", "-")], "JPY": [_row("20261028", "")]})
	rates = ecos_client.get_exchange_rates(["USD", "JPY"], client=client)
	assert [(r.currency, r.base_date) for r in rates] == [("USD", "20261027")]


# [확인 10] 모든 통화가 비면 빈 목록 (예외 없음)
def test_rates_all_empty():
	client = FakeEcos({"USD": NO_DATA, "JPY": [], "EUR": NO_DATA})
	assert ecos_client.get_exchange_rates(client=client) == []


# [확인 11] 한 통화만 API 오류가 나도 나머지 통화는 나와야 한다 (명세서: 통화별로 실패하면 그 줄만 '불러오지 못했습니다')
@pytest.mark.xfail(strict=True, reason=(
	"get_exchange_rates()가 통화별 오류를 잡지 않아, JPY 하나가 오류(ERROR-500)면 USD·EUR까지 모두 예외로 끝남"))
def test_rates_one_currency_error_keeps_others():
	client = FakeEcos({"USD": [_row("20261028", "1385.5")],
		"JPY": EcosResponseError("ERROR-500", "서버 오류"), "EUR": [_row("20261028", "1490.2")]})
	rates = ecos_client.get_exchange_rates(client=client)
	assert [r.currency for r in rates] == ["USD", "EUR"]


# =====================================================================
# 4. ECOS 통계용어 lookup_term(): 빈 결과는 None, 그 밖의 오류는 예외 (explain_term이 ExternalApiError로 바꿈)
# =====================================================================

class FakeWordClient:
	def __init__(self, result):
		self.result = result

	def search_word(self, word):
		if isinstance(self.result, Exception):
			raise self.result
		return self.result


# [확인 12] 사전에 없는 용어(INFO-200)·빈 목록은 None (용어 화면에 '찾지 못했습니다' 안내)
@pytest.mark.parametrize("result", [NO_DATA, []], ids=["INFO-200", "빈목록"])
def test_lookup_term_empty_is_none(result):
	assert ecos_client.lookup_term("없는용어", FakeWordClient(result)) is None


# [확인 13] 인증키 오류 등 다른 ECOS 오류는 예외로 올린다 (없는 용어와 구분)
def test_lookup_term_error_raises():
	with pytest.raises(EcosResponseError):
		ecos_client.lookup_term("GDP", FakeWordClient(EcosResponseError("ERROR-100", "인증키가 유효하지 않습니다")))
