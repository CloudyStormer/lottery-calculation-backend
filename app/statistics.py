from __future__ import annotations

import hashlib
import itertools
import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from scipy.stats import chisquare

from app.catalog import GameSpec, LaneSpec, PlaySpec
from app.schemas import Candidate, CandidateLane, Diagnostic, DrawRecord


@dataclass
class ProbabilityResult:
    probabilities: np.ndarray
    windows: list[int]
    validated_signal: bool
    uniformity_p_value: float
    entropy_ratio: float
    mean_abs_lag1: float


class StatisticalPredictor:
    """Regularized, walk-forward validated statistics for candidate ranking.

    The model intentionally shrinks estimates toward the uniform draw mechanism.
    Historical signals receive material weight only when their past one-step-ahead
    Brier loss beats the uniform baseline with positive paired evidence.
    """

    PRIOR_STRENGTH = 45.0
    MAX_ENUMERATED_COMBINATIONS = 80_000

    def predict(
        self,
        spec: GameSpec,
        play: PlaySpec,
        draws: list[DrawRecord],
        candidate_count: int = 3,
    ) -> tuple[list[Candidate], Diagnostic]:
        if len(draws) < 30:
            raise ValueError("至少需要30期有效历史数据才能进行统计计算")
        if spec.model_kind == "set":
            candidates, results = self._predict_set(spec, play, draws, candidate_count)
        else:
            candidates, results = self._predict_ordered(spec, play, draws, candidate_count)
        p_values = [result.uniformity_p_value for result in results]
        entropies = [result.entropy_ratio for result in results]
        correlations = [result.mean_abs_lag1 for result in results]
        windows = sorted({window for result in results for window in result.windows})
        validated = any(result.validated_signal for result in results)
        latest = draws[-1]
        diagnostic = Diagnostic(
            sample_size=len(draws),
            latest_issue=latest.issue,
            latest_date=latest.draw_date,
            windows=windows,
            uniformity_p_value=round(float(min(p_values)), 6),
            entropy_ratio=round(float(np.mean(entropies)), 6),
            mean_abs_lag1_correlation=round(float(np.mean(correlations)), 6),
            validated_signal=validated,
            validation_note=(
                "至少一个滚动窗口在时序回测中显示出正向证据，仍不代表未来优势。"
                if validated
                else "滚动窗口未稳定击败等概率基线，候选已强制向均匀分布收缩。"
            ),
        )
        return candidates, diagnostic

    def _predict_set(
        self,
        spec: GameSpec,
        play: PlaySpec,
        draws: list[DrawRecord],
        candidate_count: int,
    ) -> tuple[list[Candidate], list[ProbabilityResult]]:
        lane_candidates: list[list[tuple[tuple[int, ...], float]]] = []
        results: list[ProbabilityResult] = []
        matrices: list[np.ndarray] = []
        for lane in spec.lanes:
            matrix = self._set_matrix(draws, lane)
            result = self._fit_probability_model(matrix, lane.draw_count / lane.pool_size)
            ticket_count = play.ticket_size or lane.ticket_count
            combinations = self._rank_set_combinations(
                result.probabilities,
                matrix,
                ticket_count,
                seed=f"{spec.id}:{play.id}:{draws[-1].issue}:{lane.key}",
            )
            lane_candidates.append(combinations)
            results.append(result)
            matrices.append(matrix)

        combined: list[Candidate] = []
        selected_signatures: list[tuple[tuple[int, ...], ...]] = []
        search_depth = min(40, min(len(items) for items in lane_candidates))
        pool: list[tuple[float, tuple[tuple[int, ...], ...]]] = []
        if len(lane_candidates) == 1:
            pool = [(score, (numbers,)) for numbers, score in lane_candidates[0][:400]]
        else:
            for indexes in itertools.product(range(search_depth), repeat=len(lane_candidates)):
                selections = tuple(lane_candidates[i][index][0] for i, index in enumerate(indexes))
                score = sum(lane_candidates[i][index][1] for i, index in enumerate(indexes))
                pool.append((score, selections))
            pool.sort(key=lambda item: item[0], reverse=True)

        for raw_score, signature in pool:
            if not self._is_diverse_set(signature, selected_signatures):
                continue
            selected_signatures.append(signature)
            combined.append(
                Candidate(
                    rank=len(combined) + 1,
                    score_index=0.0,
                    lanes=[
                        CandidateLane(
                            key=lane.key,
                            label=lane.label,
                            color=lane.color,
                            numbers=[f"{number + 1:02d}" for number in signature[index]],
                        )
                        for index, lane in enumerate(spec.lanes)
                    ],
                )
            )
            combined[-1].score_index = self._score_index(raw_score, pool[0][0], len(combined))
            if len(combined) >= candidate_count:
                break
        return combined, results

    def _predict_ordered(
        self,
        spec: GameSpec,
        play: PlaySpec,
        draws: list[DrawRecord],
        candidate_count: int,
    ) -> tuple[list[Candidate], list[ProbabilityResult]]:
        values = np.asarray([draw.numbers[: len(spec.position_pool_sizes)] for draw in draws])
        position_probabilities: list[np.ndarray] = []
        results: list[ProbabilityResult] = []
        for position, pool_size in enumerate(spec.position_pool_sizes):
            matrix = np.eye(pool_size, dtype=float)[values[:, position]]
            result = self._fit_probability_model(matrix, 1.0 / pool_size)
            position_probabilities.append(result.probabilities)
            results.append(result)

        if play.id in {"group3", "group6"}:
            ranked = self._rank_grouped_digits(position_probabilities, play.id)
            minimum_distance = 1
        else:
            ranked = self._beam_sequences(position_probabilities, 5000)
            minimum_distance = max(1, len(position_probabilities) // 3)

        selected: list[tuple[int, ...]] = []
        candidates: list[Candidate] = []
        for numbers, score in ranked:
            if any(self._hamming(numbers, existing) < minimum_distance for existing in selected):
                continue
            selected.append(numbers)
            candidates.append(
                Candidate(
                    rank=len(candidates) + 1,
                    score_index=self._score_index(score, ranked[0][1], len(candidates) + 1),
                    lanes=[
                        CandidateLane(
                            key="digits",
                            label="号码",
                            color="violet",
                            numbers=[str(number) for number in numbers],
                        )
                    ],
                )
            )
            if len(candidates) >= candidate_count:
                break
        return candidates, results

    def _fit_probability_model(
        self, matrix: np.ndarray, baseline_probability: float
    ) -> ProbabilityResult:
        n, dimension = matrix.shape
        baseline = np.full(dimension, baseline_probability, dtype=float)
        possible_windows = [30, 100, 300, 1000]
        windows = sorted({min(n, window) for window in possible_windows if min(n, window) >= 20})
        evaluation_start = max(20, n - min(180, n // 3))
        accepted: list[tuple[np.ndarray, float]] = []

        for window in windows:
            losses = []
            baseline_losses = []
            for index in range(evaluation_start, n):
                start = max(0, index - window)
                train = matrix[start:index]
                estimate = self._posterior(train, baseline)
                losses.append(float(np.mean((matrix[index] - estimate) ** 2)))
                baseline_losses.append(float(np.mean((matrix[index] - baseline) ** 2)))
            differences = np.asarray(baseline_losses) - np.asarray(losses)
            mean_difference = float(np.mean(differences)) if len(differences) else 0.0
            standard_error = (
                float(np.std(differences, ddof=1) / math.sqrt(len(differences)))
                if len(differences) > 1
                else math.inf
            )
            z_score = mean_difference / standard_error if standard_error > 0 else 0.0
            estimate = self._posterior(matrix[-window:], baseline)
            if mean_difference > 0 and z_score > 1.28:
                accepted.append((estimate, min(4.0, z_score)))

        validated = bool(accepted)
        if accepted:
            total_weight = sum(weight for _, weight in accepted)
            evidence = sum(estimate * weight for estimate, weight in accepted) / total_weight
            probabilities = 0.55 * baseline + 0.45 * evidence
        else:
            fallback = self._posterior(matrix[-min(n, 300) :], baseline)
            shrinkage = min(0.14, n / (n + 7000.0))
            probabilities = (1.0 - shrinkage) * baseline + shrinkage * fallback

        probabilities = np.clip(probabilities, 1e-9, 1 - 1e-9)
        counts = matrix.sum(axis=0)
        expected = np.full(dimension, counts.sum() / dimension)
        p_value = float(chisquare(counts, expected).pvalue) if expected[0] > 0 else 1.0
        normalized = counts / max(float(counts.sum()), 1.0)
        entropy = -float(np.sum(normalized * np.log(normalized + 1e-12)))
        entropy_ratio = entropy / math.log(dimension) if dimension > 1 else 1.0
        lag1_values = []
        if n >= 3:
            for column in range(dimension):
                left = matrix[:-1, column]
                right = matrix[1:, column]
                if np.std(left) > 0 and np.std(right) > 0:
                    lag1_values.append(abs(float(np.corrcoef(left, right)[0, 1])))
        return ProbabilityResult(
            probabilities=probabilities,
            windows=windows,
            validated_signal=validated,
            uniformity_p_value=p_value,
            entropy_ratio=entropy_ratio,
            mean_abs_lag1=float(np.mean(lag1_values)) if lag1_values else 0.0,
        )

    def _posterior(self, matrix: np.ndarray, baseline: np.ndarray) -> np.ndarray:
        return (matrix.sum(axis=0) + self.PRIOR_STRENGTH * baseline) / (
            len(matrix) + self.PRIOR_STRENGTH
        )

    @staticmethod
    def _set_matrix(draws: list[DrawRecord], lane: LaneSpec) -> np.ndarray:
        matrix = np.zeros((len(draws), lane.pool_size), dtype=float)
        for row, draw in enumerate(draws):
            lane_numbers = draw.numbers[lane.start_index : lane.start_index + lane.draw_count]
            for number in lane_numbers:
                if 1 <= number <= lane.pool_size:
                    matrix[row, number - 1] = 1.0
        return matrix

    def _rank_set_combinations(
        self,
        probabilities: np.ndarray,
        matrix: np.ndarray,
        ticket_count: int,
        seed: str,
    ) -> list[tuple[tuple[int, ...], float]]:
        pool_size = len(probabilities)
        cap = min(pool_size, max(ticket_count + 8, 16 if ticket_count >= 5 else 12))
        ranked_numbers = sorted(
            range(pool_size),
            key=lambda index: (probabilities[index], self._tie_break(seed, index)),
            reverse=True,
        )[:cap]
        while math.comb(len(ranked_numbers), ticket_count) > self.MAX_ENUMERATED_COMBINATIONS:
            ranked_numbers.pop()

        pair_scores = self._pair_scores(matrix)
        ranked: list[tuple[tuple[int, ...], float]] = []
        for combination in itertools.combinations(ranked_numbers, ticket_count):
            number_score = sum(math.log(probabilities[index]) for index in combination)
            pair_score = sum(
                pair_scores[left, right] for left, right in itertools.combinations(combination, 2)
            )
            jitter = self._combination_jitter(seed, combination)
            ranked.append((tuple(sorted(combination)), number_score + 0.035 * pair_score + jitter))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    @staticmethod
    def _pair_scores(matrix: np.ndarray) -> np.ndarray:
        n = max(len(matrix), 1)
        frequencies = matrix.mean(axis=0)
        observed = matrix.T @ matrix
        expected = np.outer(frequencies, frequencies) * n
        scores = np.log((observed + 2.0) / (expected + 2.0))
        np.fill_diagonal(scores, 0.0)
        return np.clip(scores, -0.35, 0.35)

    def _rank_grouped_digits(
        self, probabilities: list[np.ndarray], play_id: str
    ) -> list[tuple[tuple[int, ...], float]]:
        ranked = []
        for combination in itertools.combinations_with_replacement(range(10), 3):
            counts = sorted({combination.count(value) for value in combination}, reverse=True)
            if play_id == "group3" and counts != [2, 1]:
                continue
            if play_id == "group6" and len(set(combination)) != 3:
                continue
            permutations = set(itertools.permutations(combination))
            probability = sum(
                math.prod(probabilities[position][value] for position, value in enumerate(order))
                for order in permutations
            )
            ranked.append((combination, math.log(max(probability, 1e-12))))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    @staticmethod
    def _beam_sequences(
        probabilities: list[np.ndarray], beam_size: int
    ) -> list[tuple[tuple[int, ...], float]]:
        beam: list[tuple[tuple[int, ...], float]] = [((), 0.0)]
        for position_probabilities in probabilities:
            expanded = [
                (prefix + (number,), score + math.log(max(float(probability), 1e-12)))
                for prefix, score in beam
                for number, probability in enumerate(position_probabilities)
            ]
            expanded.sort(key=lambda item: item[1], reverse=True)
            beam = expanded[:beam_size]
        return beam

    @staticmethod
    def _hamming(left: Iterable[int], right: Iterable[int]) -> int:
        return sum(a != b for a, b in zip(left, right, strict=True))

    @staticmethod
    def _is_diverse_set(
        signature: tuple[tuple[int, ...], ...],
        existing: list[tuple[tuple[int, ...], ...]],
    ) -> bool:
        for other in existing:
            too_similar = True
            for current_lane, other_lane in zip(signature, other, strict=True):
                allowed_overlap = max(0, len(current_lane) - 1)
                if len(set(current_lane) & set(other_lane)) <= allowed_overlap:
                    too_similar = False
                    break
            if too_similar:
                return False
        return True

    @staticmethod
    def _tie_break(seed: str, value: int) -> float:
        digest = hashlib.sha256(f"{seed}:{value}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    @staticmethod
    def _combination_jitter(seed: str, values: tuple[int, ...]) -> float:
        digest = hashlib.sha256(f"{seed}:{values}".encode()).digest()
        return (int.from_bytes(digest[:4], "big") / 2**32) * 1e-9

    @staticmethod
    def _score_index(score: float, best_score: float, rank: int) -> float:
        relative = math.exp(min(0.0, score - best_score))
        return round(max(72.0, min(99.0, 96.0 * relative - (rank - 1) * 1.7)), 1)
