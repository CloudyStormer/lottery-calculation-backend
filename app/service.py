from __future__ import annotations

from datetime import datetime, timezone

from app.catalog import GAMES, GameSpec, PlaySpec
from app.config import Settings
from app.providers import OfficialDataError, OfficialDataProvider
from app.schemas import GenerateResponse, SyncResponse
from app.statistics import StatisticalPredictor
from app.storage import DrawStore


class GameNotFoundError(KeyError):
    pass


class PlayNotFoundError(KeyError):
    pass


class InsufficientDataError(RuntimeError):
    pass


class LotteryService:
    def __init__(
        self,
        settings: Settings,
        store: DrawStore | None = None,
        provider: OfficialDataProvider | None = None,
        predictor: StatisticalPredictor | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or DrawStore(settings.database_path)
        self.provider = provider or OfficialDataProvider(settings.http_timeout)
        self.predictor = predictor or StatisticalPredictor()

    def game(self, game_id: str) -> GameSpec:
        try:
            return GAMES[game_id]
        except KeyError as exc:
            raise GameNotFoundError(game_id) from exc

    @staticmethod
    def play(spec: GameSpec, play_id: str | None) -> PlaySpec:
        selected = play_id or spec.plays[0].id
        for play in spec.plays:
            if play.id == selected:
                return play
        raise PlayNotFoundError(selected)

    def sync(self, game_id: str, full: bool = False) -> SyncResponse:
        spec = self.game(game_id)
        limit = None if full else self.settings.history_limit
        records = self.provider.fetch(spec, limit)
        stored = self.store.upsert_many(records)
        latest = max(records, key=lambda item: (item.draw_date, item.issue)) if records else None
        return SyncResponse(
            game_id=game_id,
            fetched=len(records),
            stored=stored,
            latest_issue=latest.issue if latest else None,
            synced_at=datetime.now(timezone.utc),
        )

    def generate(
        self, game_id: str, play_id: str | None, refresh: bool = False
    ) -> GenerateResponse:
        spec = self.game(game_id)
        play = self.play(spec, play_id)
        warnings = [
            "开奖结果具有随机性，统计候选不构成中奖承诺或投资建议。",
            "候选评分是模型内部相对指数，不是中奖概率。",
        ]
        cached_count = self.store.count(game_id)
        if refresh or cached_count < 100:
            try:
                self.sync(game_id)
            except OfficialDataError as exc:
                if cached_count < 30:
                    raise InsufficientDataError(str(exc)) from exc
                warnings.append(f"官方同步暂时失败，本次使用本地缓存：{exc}")
        draws = self.store.get_draws(game_id, self.settings.history_limit)
        if len(draws) < 30:
            raise InsufficientDataError("可用历史数据不足30期")
        candidates, diagnostic = self.predictor.predict(spec, play, draws)
        return GenerateResponse(
            game_id=spec.id,
            game_name=spec.name,
            play_id=play.id,
            play_name=play.name,
            generated_at=datetime.now(timezone.utc),
            candidates=candidates,
            diagnostic=diagnostic,
            data_source="国家体育总局体育彩票管理中心官网"
            if spec.provider == "sport"
            else "中国福利彩票发行管理中心官网",
            official_url=spec.official_url,
            methodology=[
                "30/100/300/1000期多尺度滚动窗口",
                "贝叶斯先验收缩，防止把短期冷热误判为规律",
                "严格按时间顺序的一步向前Brier损失回测",
                "卡方均匀性、信息熵与滞后一阶相关诊断",
                "组合共现项正则化与候选多样性约束",
            ],
            warnings=warnings,
        )
