"""ECOS API · call_ecos, get_ecos_exchange_rate, get_ecos_statistic_table_list, get_ecos_statistic_item_list, get_ecos_statistic_data, get_ecos_statistic_word (류현수)"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import httpx
from datetime import date, timedelta

from hri.config.settings import load_settings
from hri.domain.schemas.external import EcosExchangeRate
from hri.exception.errors import ExternalApiError

BASE_URL = "https://ecos.bok.or.kr/api"

def call_ecos(service: str, *params: str, start: int = 1, end: int = 100, timeout=10) -> dict:
    # key load
    key = load_settings().ecos_api_key
    if not key:
        raise ExternalApiError("ECOS_API_KEY가 설정되지 않았습니다.")

    # 요청 인자 (서미스명, 인증키, 요청유형, 언어구분, 요청시작건수, 요청종료 건수)
    # ref: https://ecos.bok.or.kr/api/#/DevGuide/DevSpeciflcation
    parts = [service, key, "json", "kr", str(start), str(end)]
    parts += [urllib.parse.quote(str(p)) for p in params]
    url = BASE_URL + "/" + "/".join(parts)

    # api 요청 후 에러 종류 별 처리
    try:
        res = httpx.get(url, timeout=timeout)
        res.raise_for_status()
        body = res.json()
    except httpx.HTTPStatusError as e:
        raise ExternalApiError(f"ECOS 호출 실패(HTTP {e.response.status_code})")
    except httpx.TimeoutException:
        raise ExternalApiError(f"ECOS 연결 실패(Timeout, {timeout}sec)")
    except httpx.RequestError as e:
        raise ExternalApiError(f"ECOS 연결 실패({type(e).__name__})")
    except ValueError:
        raise ExternalApiError("ECOS 응답을 해석하지 못했습니다.")

    # 결과 반환
    if "RESULT" in body:
        code = body["RESULT"].get("CODE", "")
        if code=="INFO-200":    # 정상응답
            return {"row": []}

        # ECOS에서 오류 응답이 온 경우
        raise ExternalApiError(f"ECOS 오류 {code}: {body['RESULT'].get('MESSAGE', '')}")
    
    return body.get(service, {"row": []})

def get_ecos_exchange_rate(currency: str = "USD") -> EcosExchangeRate:
    cur = currency.upper()
    item, 

def get_ecos_statistic_table_list():
    res = call_ecos("StatisticTableList")
    print(res)
    return res

def get_ecos_statistic_item_list():
    pass
    

def get_ecos_statistic_data():
    pass

def get_ecos_statistic_word():
    pass
