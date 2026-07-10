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
            "每期开奖相互独立，历史结果不会改变下一期任何合法单注的理论概率。",
            "彩票长期期望由各玩法返奖结构决定；奖金计提比例不等于个人返还率。",
            "候选仅为等概率随机样本，不构成中奖预测、承诺或投资建议。",
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
            theoretical_odds=play.odds_text,
            generated_at=datetime.now(timezone.utc),
            candidates=candidates,
            diagnostic=diagnostic,
            data_source="国家体育总局体育彩票管理中心官网"
            if spec.provider == "sport"
            else "中国福利彩票发行管理中心官网",
            official_url=spec.official_url,
            methodology=[
                "按官方规则精确计算组合样本空间与单注理论概率",
                "30/100/300/1000期窗口仅用于随机性审计",
                "卡方均匀性、信息熵与滞后一阶相关诊断",
                "严格时序Brier损失检验历史模型是否只是过拟合",
                "使用系统加密安全随机源，对所有合法单注等概率抽样",
            ],
            warnings=warnings,
        )
