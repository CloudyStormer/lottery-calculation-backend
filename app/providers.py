from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date, datetime
from typing import Any

import httpx

from app.catalog import GameSpec
from app.schemas import DrawRecord


class OfficialDataError(RuntimeError):
    pass


class OfficialDataProvider:
    SPORT_API = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
    WELFARE_API = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
    )

    def __init__(self, timeout: float = 25.0) -> None:
        self.timeout = timeout

    def fetch(self, spec: GameSpec, limit: int | None) -> list[DrawRecord]:
        if spec.provider == "sport":
            return self._fetch_sport(spec, limit)
        return self._fetch_welfare(spec, limit)

    def _client(self, referer: str) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": referer,
                "User-Agent": self.USER_AGENT,
            },
        )

    def _fetch_sport(self, spec: GameSpec, limit: int | None) -> list[DrawRecord]:
        page_size = 100
        page_no = 1
        records: list[DrawRecord] = []
        referer = f"https://m.lottery.gov.cn/mkj{spec.id}/"
        with self._client(referer) as client:
            while True:
                params = {
                    "gameNo": spec.provider_code,
                    "provinceId": "0",
                    "pageSize": str(page_size),
                    "isVerify": "1",
                    "termLimits": "0",
                    "pageNo": str(page_no),
                }
                payload = self._get_json(
                    client,
                    self.SPORT_API,
                    params,
                    referer,
                    "中国体彩网",
                )
                if str(payload.get("errorCode")) != "0":
                    raise OfficialDataError(
                        f"中国体彩网返回错误：{payload.get('errorMessage', '未知错误')}"
                    )
                value = payload.get("value") or {}
                items = value.get("list") or []
                records.extend(self._parse_sport_items(spec, items))
                pages = int(value.get("pages") or 1)
                if page_no >= pages or (limit and len(records) >= limit):
                    break
                page_no += 1
        if limit:
            records = records[:limit]
        records.sort(key=lambda item: (item.draw_date, item.issue))
        return records

    def _parse_sport_items(self, spec: GameSpec, items: list[dict[str, Any]]) -> list[DrawRecord]:
        records = []
        for item in items:
            result = str(item.get("lotteryDrawResult") or "").strip()
            if not result:
                continue
            raw_date = str(item.get("lotteryDrawTime") or "").split(" ")[0]
            try:
                draw_date = date.fromisoformat(raw_date)
                numbers = [int(value) for value in result.split()]
            except (TypeError, ValueError):
                continue
            records.append(
                DrawRecord(
                    game_id=spec.id,
                    issue=str(item.get("lotteryDrawNum")),
                    draw_date=draw_date,
                    numbers=numbers,
                    source_url=spec.official_url,
                )
            )
        return records

    def _fetch_welfare(self, spec: GameSpec, limit: int | None) -> list[DrawRecord]:
        params = {
            "name": spec.provider_code,
            "issueCount": "",
            "issueStart": "",
            "issueEnd": "",
            "dayStart": "",
            "dayEnd": "",
            "pageNo": "1",
            "pageSize": "30",
            "week": "",
            "systemType": "",
        }
        referer = "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/"
        with self._client(referer) as client:
            payload = self._get_json(client, self.WELFARE_API, params, referer, "中国福彩网")
        if int(payload.get("state", -1)) != 0:
            raise OfficialDataError(f"中国福彩网返回错误：{payload.get('message', '未知错误')}")
        records = self._parse_welfare_items(spec, payload.get("result") or [])
        if limit:
            records = records[:limit]
        records.sort(key=lambda item: (item.draw_date, item.issue))
        return records

    def _parse_welfare_items(self, spec: GameSpec, items: list[dict[str, Any]]) -> list[DrawRecord]:
        records = []
        for item in items:
            try:
                red = [int(value) for value in str(item.get("red") or "").split(",") if value]
                blue = [int(value) for value in str(item.get("blue") or "").split(",") if value]
                raw_date = str(item.get("date") or "").split("(")[0]
                draw_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue
            if not red:
                continue
            records.append(
                DrawRecord(
                    game_id=spec.id,
                    issue=str(item.get("code")),
                    draw_date=draw_date,
                    numbers=red + blue,
                    source_url=spec.official_url,
                )
            )
        return records

    def _get_json(
        self,
        client: httpx.Client,
        url: str,
        params: dict[str, str],
        referer: str,
        source: str,
    ) -> dict[str, Any]:
        response: httpx.Response | None = None
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "json" in content_type.lower() or response.text.lstrip().startswith("{"):
                return response.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            pass

        # The sports-lottery WAF occasionally rejects Python TLS fingerprints while
        # accepting the same low-frequency request from curl. Keep this narrow fallback
        # so deployments can still use the public official endpoint without a proxy.
        curl = shutil.which("curl")
        if not curl:
            status = response.status_code if response is not None else "network error"
            raise OfficialDataError(f"{source}访问失败（{status}），且系统未安装curl")
        request_url = str(httpx.URL(url, params=params))
        command = [
            curl,
            "-L",
            "--max-time",
            str(int(self.timeout)),
            "-sS",
            "--fail-with-body",
            "-H",
            "Accept: application/json, text/javascript, */*; q=0.01",
            "-H",
            f"Referer: {referer}",
            "-H",
            f"User-Agent: {self.USER_AGENT}",
            request_url,
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout + 3,
            )
            payload = json.loads(completed.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise OfficialDataError(f"{source}未返回有效数据，可能触发了访问保护") from exc
        if not isinstance(payload, dict):
            raise OfficialDataError(f"{source}返回的数据结构无效")
        return payload
