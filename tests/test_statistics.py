from datetime import date, timedelta

import numpy as np

from app.catalog import GAMES
from app.schemas import DrawRecord
from app.statistics import StatisticalPredictor


def make_set_draws(game_id: str, count: int = 360) -> list[DrawRecord]:
    spec = GAMES[game_id]
    rng = np.random.default_rng(20260710)
    records = []
    for index in range(count):
        numbers: list[int] = []
        for lane in spec.lanes:
            selected = rng.choice(lane.pool_size, lane.draw_count, replace=False) + 1
            numbers.extend(sorted(int(value) for value in selected))
        records.append(
            DrawRecord(
                game_id=game_id,
                issue=f"{index + 1:05d}",
                draw_date=date(2020, 1, 1) + timedelta(days=index),
                numbers=numbers,
                source_url="https://example.test",
            )
        )
    return records


def make_digit_draws(game_id: str, count: int = 360) -> list[DrawRecord]:
    spec = GAMES[game_id]
    rng = np.random.default_rng(20260710)
    return [
        DrawRecord(
            game_id=game_id,
            issue=f"{index + 1:05d}",
            draw_date=date(2020, 1, 1) + timedelta(days=index),
            numbers=[int(rng.integers(0, size)) for size in spec.position_pool_sizes],
            source_url="https://example.test",
        )
        for index in range(count)
    ]


def test_dlt_predictions_follow_pool_rules_and_are_unique() -> None:
    spec = GAMES["dlt"]
    candidates, diagnostic = StatisticalPredictor().predict(
        spec, spec.plays[0], make_set_draws("dlt")
    )
    assert len(candidates) == 3
    assert diagnostic.sample_size == 360
    signatures = set()
    for candidate in candidates:
        front = candidate.lanes[0].numbers
        back = candidate.lanes[1].numbers
        assert len(front) == len(set(front)) == 5
        assert len(back) == len(set(back)) == 2
        assert all(1 <= int(value) <= 35 for value in front)
        assert all(1 <= int(value) <= 12 for value in back)
        signatures.add((tuple(front), tuple(back)))
    assert len(signatures) == 3


def test_group3_and_group6_constraints() -> None:
    predictor = StatisticalPredictor()
    spec = GAMES["fc3d"]
    draws = make_digit_draws("fc3d")
    group3, _ = predictor.predict(spec, spec.plays[1], draws)
    group6, _ = predictor.predict(spec, spec.plays[2], draws)
    assert all(
        sorted(
            {lane.numbers.count(number) for number in set(lane.numbers)},
            reverse=True,
        )
        == [2, 1]
        for candidate in group3
        for lane in candidate.lanes
    )
    assert all(len(set(candidate.lanes[0].numbers)) == 3 for candidate in group6)


def test_qxc_accepts_current_back_number_range_and_generates_legal_tickets() -> None:
    predictor = StatisticalPredictor()
    spec = GAMES["qxc"]
    draws = make_digit_draws("qxc")
    assert any(draw.numbers[-1] >= 10 for draw in draws)

    candidates, diagnostic = predictor.predict(spec, spec.plays[0], draws)

    assert diagnostic.sample_size == len(draws)
    assert len(candidates) == 3
    for candidate in candidates:
        numbers = [int(value) for value in candidate.lanes[0].numbers]
        assert len(numbers) == 7
        assert all(0 <= number <= 9 for number in numbers[:6])
        assert 0 <= numbers[-1] <= 14


def test_happy8_respects_selected_ticket_size() -> None:
    spec = GAMES["kl8"]
    candidates, _ = StatisticalPredictor().predict(spec, spec.plays[4], make_set_draws("kl8"))
    assert all(len(candidate.lanes[0].numbers) == 5 for candidate in candidates)
