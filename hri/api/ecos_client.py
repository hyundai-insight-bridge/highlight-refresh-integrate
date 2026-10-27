""" external 스키마에 맞추기,  """

from datetime import date, timedelta

from ecos import Cycle, EcosClient
from ecos.exceptions import EcosResponseError
from ecos.models import StatisticRow

from hri.config.settings import load_settings
from hri.domain.schemas.external import EcosExchangeRate, EcosQuery, Indicator

EXCHANGE_STAT_CODE = "731Y001"
CURRENCY_ITEM_CODES = {"USD": "0000001", "JPY(100엔)": "0000002", "EUR": "0000003"}

client = EcosClient(load_settings.ecos_api_key)

# 특정 날짜의 환율을 조회
date_formatter = lambda x: str(x).replace("-", "")
today = date.today()
for r in client.search("731Y001", Cycle.DAILY, date_formatter(today), date_formatter(today), end_num=10):
    print(f"  {r.time} | {r.item_name1:<25} | {r.data_value} {r.unit_name}")

# 특정 단어의 의미를 조회
for w in client.search_word("GDP"):
    content = w.content.replace("\n", " ")
    print(f"  {w.word}: {content}...")

# 통계표 목록 조회
print("="*50)
print(client.list_tables())

# 통계 항목 조회
print("="*50)
print(client.list_items("901Y054"))

# 통계 데이터 조회(연간)
print("="*50)
print(client.search("901Y054", Cycle.ANNUAL, "2022", "2023"))

print(client.list_items("731Y001"))