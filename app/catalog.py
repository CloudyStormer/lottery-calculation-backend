from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Provider = Literal["sport", "welfare"]
ModelKind = Literal["set", "ordered"]


@dataclass(frozen=True)
class LaneSpec:
    key: str
    label: str
    pool_size: int
    draw_count: int
    ticket_count: int
    start_index: int
    color: str


@dataclass(frozen=True)
class PlaySpec:
    id: str
    name: str
    description: str
    ticket_size: int | None = None
    odds_text: str = ""


@dataclass(frozen=True)
class GameSpec:
    id: str
    name: str
    issuer: Literal["sports", "welfare"]
    category: str
    model_kind: ModelKind
    provider: Provider
    provider_code: str
    official_url: str
    rule_summary: str
    lanes: tuple[LaneSpec, ...]
    plays: tuple[PlaySpec, ...]
    position_pool_sizes: tuple[int, ...] = ()
    history_note: str = ""


GAMES: dict[str, GameSpec] = {
    "dlt": GameSpec(
        id="dlt",
        name="超级大乐透",
        issuer="sports",
        category="乐透型",
        model_kind="set",
        provider="sport",
        provider_code="85",
        official_url="https://m.lottery.gov.cn/ksjz/m/yxgz_dlt/",
        rule_summary="前区01—35选5，后区01—12选2。",
        lanes=(
            LaneSpec("front", "前区", 35, 5, 5, 0, "blue"),
            LaneSpec("back", "后区", 12, 2, 2, 5, "gold"),
        ),
        plays=(
            PlaySpec(
                "basic",
                "基本投注",
                "5个前区号码 + 2个后区号码",
                odds_text="一等奖：1 / [C(35,5) × C(12,2)] = 1 / 21,425,712",
            ),
        ),
        history_note="官方接口可追溯至07001期。",
    ),
    "pl3": GameSpec(
        id="pl3",
        name="排列3",
        issuer="sports",
        category="数字型",
        model_kind="ordered",
        provider="sport",
        provider_code="35",
        official_url="https://m.lottery.gov.cn/zst/pls/",
        rule_summary="从000—999中选择一个三位数；支持直选、组选3和组选6。",
        lanes=(),
        plays=(
            PlaySpec("direct", "直选", "百、十、个位全部按顺序匹配", odds_text="单注：1 / 1000"),
            PlaySpec(
                "group3",
                "组选3",
                "三个数字中有两个相同，顺序不限",
                odds_text="单注：3 / 1000（约1 / 333.33）",
            ),
            PlaySpec(
                "group6",
                "组选6",
                "三个数字各不相同，顺序不限",
                odds_text=(
                    "单注：6 / 1000（约1 / 166.67）；720 / 1000是所有组六形态占比，并非单注中奖率"
                ),
            ),
        ),
        position_pool_sizes=(10, 10, 10),
        history_note="官方接口可追溯至04001期。",
    ),
    "pl5": GameSpec(
        id="pl5",
        name="排列5",
        issuer="sports",
        category="数字型",
        model_kind="ordered",
        provider="sport",
        provider_code="350133",
        official_url="https://m.lottery.gov.cn/ksjz/plw/guize/",
        rule_summary="从00000—99999中选择一个五位数，按顺序匹配。",
        lanes=(),
        plays=(
            PlaySpec("direct", "直选", "五个位置全部按顺序匹配", odds_text="单注：1 / 100,000"),
        ),
        position_pool_sizes=(10, 10, 10, 10, 10),
        history_note="官方接口可追溯至04001期。",
    ),
    "qxc": GameSpec(
        id="qxc",
        name="7星彩",
        issuer="sports",
        category="乐透型",
        model_kind="ordered",
        provider="sport",
        provider_code="04",
        official_url="https://m.lottery.gov.cn/tcwm/qxc/",
        rule_summary="前六位分别从0—9中选择，最后一位从0—14中选择。",
        lanes=(),
        plays=(
            PlaySpec(
                "basic",
                "基本投注",
                "前六位数字 + 1个0—14后区号码",
                odds_text="一等奖：1 / (10^6 × 15) = 1 / 15,000,000",
            ),
        ),
        position_pool_sizes=(10, 10, 10, 10, 10, 10, 15),
        history_note="官方接口可追溯至04101期。",
    ),
    "ssq": GameSpec(
        id="ssq",
        name="双色球",
        issuer="welfare",
        category="乐透型",
        model_kind="set",
        provider="welfare",
        provider_code="ssq",
        official_url="https://www.cwl.gov.cn/fcpz/yxjs/ssq/",
        rule_summary="红球01—33选6，蓝球01—16选1。",
        lanes=(
            LaneSpec("red", "红球", 33, 6, 6, 0, "red"),
            LaneSpec("blue", "蓝球", 16, 1, 1, 6, "blue"),
        ),
        plays=(
            PlaySpec(
                "basic",
                "单式投注",
                "6个红球号码 + 1个蓝球号码",
                odds_text="一等奖：1 / [C(33,6) × 16] = 1 / 17,721,088",
            ),
        ),
        history_note="当前官方接口可取得2013年至今数据。",
    ),
    "fc3d": GameSpec(
        id="fc3d",
        name="福彩3D",
        issuer="welfare",
        category="数字型",
        model_kind="ordered",
        provider="welfare",
        provider_code="3d",
        official_url="https://www.cwl.gov.cn/fcpz/yxjs/3d/",
        rule_summary="三个位置分别从0—9中选择；支持直选、组选3和组选6。",
        lanes=(),
        plays=(
            PlaySpec("direct", "直选", "百、十、个位全部按顺序匹配", odds_text="单注：1 / 1000"),
            PlaySpec(
                "group3",
                "组选3",
                "三个数字中有两个相同，顺序不限",
                odds_text="单注：3 / 1000（约1 / 333.33）",
            ),
            PlaySpec(
                "group6",
                "组选6",
                "三个数字各不相同，顺序不限",
                odds_text=(
                    "单注：6 / 1000（约1 / 166.67）；720 / 1000是所有组六形态占比，并非单注中奖率"
                ),
            ),
        ),
        position_pool_sizes=(10, 10, 10),
        history_note="当前官方接口可取得2013年至今数据。",
    ),
    "qlc": GameSpec(
        id="qlc",
        name="七乐彩",
        issuer="welfare",
        category="乐透型",
        model_kind="set",
        provider="welfare",
        provider_code="qlc",
        official_url="https://www.cwl.gov.cn/fcpz/yxjs/qlc/",
        rule_summary="从01—30中选择7个基本号码；特别号码由开奖产生，不参与选号。",
        lanes=(LaneSpec("main", "基本号", 30, 7, 7, 0, "red"),),
        plays=(
            PlaySpec(
                "basic",
                "单式投注",
                "从01—30中选择7个号码",
                odds_text="一等奖：1 / C(30,7) = 1 / 2,035,800，并非1 / 61,074,000",
            ),
        ),
        history_note="当前官方接口可取得2013年至今数据。",
    ),
    "kl8": GameSpec(
        id="kl8",
        name="快乐8",
        issuer="welfare",
        category="基诺型",
        model_kind="set",
        provider="welfare",
        provider_code="kl8",
        official_url="https://www.cwl.gov.cn/fcpz/yxjs/kl8/",
        rule_summary="从01—80中选择1至10个号码，每期摇出20个开奖号码。",
        lanes=(LaneSpec("main", "选号", 80, 20, 10, 0, "red"),),
        plays=tuple(
            PlaySpec(
                f"pick{size}",
                f"选{size}",
                f"从01—80中选择{size}个号码",
                size,
                (
                    f"所选{size}个号码全部命中：C(20,{size}) / C(80,{size}) "
                    f"≈ 1 / {math.comb(80, size) / math.comb(20, size):,.2f}；"
                    "其他奖级按超几何分布计算"
                ),
            )
            for size in range(1, 11)
        ),
        history_note="官方接口可取得快乐8上市以来数据。",
    ),
}


def public_catalog() -> dict[str, object]:
    issuers = [
        {
            "id": "sports",
            "name": "中国体育彩票",
            "shortName": "体彩",
            "theme": "blue",
            "officialUrl": "https://m.lottery.gov.cn/zs/wfjs/",
        },
        {
            "id": "welfare",
            "name": "中国福利彩票",
            "shortName": "福彩",
            "theme": "red",
            "officialUrl": "https://www.cwl.gov.cn/fcpz/yxjs/",
        },
    ]
    games = []
    for spec in GAMES.values():
        games.append(
            {
                "id": spec.id,
                "name": spec.name,
                "issuer": spec.issuer,
                "category": spec.category,
                "modelKind": spec.model_kind,
                "officialUrl": spec.official_url,
                "ruleSummary": spec.rule_summary,
                "historyNote": spec.history_note,
                "plays": [
                    {
                        "id": play.id,
                        "name": play.name,
                        "description": play.description,
                        "ticketSize": play.ticket_size,
                        "oddsText": play.odds_text,
                    }
                    for play in spec.plays
                ],
            }
        )
    return {"issuers": issuers, "games": games}
