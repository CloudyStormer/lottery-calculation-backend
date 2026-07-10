from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.catalog import public_catalog
from app.config import load_settings
from app.schemas import GenerateRequest, GenerateResponse, SyncResponse
from app.service import (
    GameNotFoundError,
    InsufficientDataError,
    LotteryService,
    PlayNotFoundError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    app.state.service = LotteryService(settings)
    yield


app = FastAPI(
    title="数研选号 API",
    version="0.1.0",
    description="基于官方历史开奖、带时序回测与概率收缩的统计候选服务。",
    lifespan=lifespan,
)

settings = load_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def service(request: Request) -> LotteryService:
    return request.app.state.service


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/catalog")
def catalog() -> dict[str, object]:
    return public_catalog()


@app.get("/api/v1/data-status")
def data_status(request: Request) -> dict[str, object]:
    current = service(request)
    indexed = {item["game_id"]: item for item in current.store.statuses()}
    return {
        "games": [
            {
                "gameId": game_id,
                "recordCount": indexed.get(game_id, {}).get("record_count", 0),
                "latestIssue": indexed.get(game_id, {}).get("latest_issue"),
                "syncedAt": indexed.get(game_id, {}).get("synced_at"),
            }
            for game_id in current_game_ids()
        ]
    }


def current_game_ids() -> list[str]:
    return list(public_catalog_game_ids())


def public_catalog_game_ids():
    return (game["id"] for game in public_catalog()["games"])


@app.post("/api/v1/games/{game_id}/sync", response_model=SyncResponse)
def sync_game(
    game_id: str,
    request: Request,
    full: bool = Query(False, description="抓取官网当前可提供的完整历史"),
) -> SyncResponse:
    try:
        return service(request).sync(game_id, full=full)
    except GameNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到该玩法") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"官方数据同步失败：{exc}") from exc


@app.post("/api/v1/games/{game_id}/generate", response_model=GenerateResponse)
def generate(game_id: str, payload: GenerateRequest, request: Request) -> GenerateResponse:
    try:
        return service(request).generate(game_id, payload.play_id, payload.refresh)
    except GameNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到该玩法") from exc
    except PlayNotFoundError as exc:
        raise HTTPException(status_code=422, detail="该投注方式不属于当前玩法") from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
