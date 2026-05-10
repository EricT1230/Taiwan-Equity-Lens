from __future__ import annotations

import time
from typing import Callable, Protocol
from urllib.request import Request, urlopen


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        headers: dict[str, str],
        cookies: dict[str, str],
        timeout: int,
    ) -> str:
        ...


class UrllibHttpClient:
    def get(
        self,
        url: str,
        headers: dict[str, str],
        cookies: dict[str, str],
        timeout: int,
    ) -> str:
        cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
        request_headers = dict(headers)
        request_headers["Cookie"] = cookie_header
        request = Request(url, headers=request_headers)
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
        return body.decode("utf-8", errors="replace")


class GoodinfoClient:
    def __init__(
        self,
        http_client: HttpClient | None = None,
        now: Callable[[], float] = time.time,
        timeout: int = 15,
    ) -> None:
        self.http_client = http_client or UrllibHttpClient()
        self.now = now
        self.timeout = timeout

    def get_client_key(self) -> tuple[str, float]:
        tz_offset = -480
        now_ms = self.now() * 1000
        days_since_epoch = now_ms / 86400000
        days_adjusted = days_since_epoch - tz_offset / 1440
        client_key = f"2.8|38057.1435627105|46946.0324515993|{tz_offset}|{days_adjusted}|{days_adjusted}"
        return client_key, days_adjusted

    def fetch_report(self, stock_id: str, report_category: str) -> str:
        client_key, days_adjusted = self.get_client_key()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://goodinfo.tw/",
        }
        cookies = {"CLIENT_KEY": client_key}
        url = (
            "https://goodinfo.tw/tw/StockFinDetail.asp?"
            f"RPT_CAT={report_category}&STOCK_ID={stock_id}&REINIT={days_adjusted:.10f}"
        )
        return self.http_client.get(url, headers=headers, cookies=cookies, timeout=self.timeout)


def build_metadata(stock_id: str, years: list[str]) -> dict[str, object]:
    return {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "source": "Goodinfo.tw",
        "source_urls": {
            "income_statement": f"https://goodinfo.tw/tw/StockFinDetail.asp?RPT_CAT=IS_YEAR&STOCK_ID={stock_id}",
            "balance_sheet": f"https://goodinfo.tw/tw/StockFinDetail.asp?RPT_CAT=BS_YEAR&STOCK_ID={stock_id}",
            "cash_flow": f"https://goodinfo.tw/tw/StockFinDetail.asp?RPT_CAT=CF_YEAR&STOCK_ID={stock_id}",
        },
        "mops_url": f"https://mops.twse.com.tw/mops/web/t05st01?step=1&co_id={stock_id}&TYPEK=sii",
        "mops_url_otc": f"https://mops.twse.com.tw/mops/web/t05st01?step=1&co_id={stock_id}&TYPEK=otc",
        "years_covered": years,
        "currency": "TWD 億元",
    }
