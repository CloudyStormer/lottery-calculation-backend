from __future__ import annotations

import itertools
import math
import secrets
from dataclasses import dataclass

import numpy as np
from scipy.stats import chisquare

from app.catalog import GameSpec, LaneSpec, PlaySpec
from app.schemas import Candidate, CandidateLane, Diagnostic, DrawRecord


@dataclass
class AuditResult:
    windows: list[int]
    anomaly_detected: bool
    uniformity_p_value: float
    entropy_ratio: float
    mean_abs_lag1: float


class StatisticalPredictor:
    """Audit historical randomness, then generate strictly equal-probability tickets.

    Historical draws are never used to increase or decrease a legal number's sampling
    weight. They only feed descriptive tests for uniformity and serial dependence.
    This separation prevents an exploratory anomaly from being misrepresented as a
    repeatable forecasting edge.
    """

    PRIOR_STRENGTH = 45.0

    def __init__(self) -> None:
        self.random = secrets.SystemRandom()

    def predict(
        self,
        spec: GameSpec,
        play: PlaySpec,
        draws: list[DrawRecord],
        candidate_count: int = 3,
    ) -> tuple[list[Candidate], Diagnostic]:
        if len(draws) < 30:
            raise ValueError("至少需要30期有效历史数据才能进行随机性审计")
        if spec.model_kind == "set":
            candidates, audits = self._predict_set(spec, play, draws, candidate_count)
        else:
            candidates, audits = self._predict_ordered(spec, play, draws, candidate_count)

        p_values = [audit.uniformity_p_value for audit in audits]
        entropies = [audit.entropy_ratio for audit in audits]
        correlations = [audit.mean_abs_lag1 for audit in audits]
        windows = sorted({window for audit in audits for window in audit.windows})
        anomaly = any(audit.anomaly_detected for audit in audits)
        latest = draws[-1]
        diagnostic = Diagnostic(
            sample_size=len(draws),
            latest_issue=latest.issue,
            latest_date=latest.draw_date,
            windows=windows,
            uniformity_p_value=round(float(min(p_values)), 6),
            entropy_ratio=round(float(np.mean(entropies)), 6),
            mean_abs_lag1_correlation=round(float(np.mean(correlations)), 6),
            validated_signal=anomaly,
            validation_note=(
                "历史样本出现需要复核的统计偏离；它可能来自随机波动、规则变化或数据质量，"
                "不进入选号权重，也不代表下一期可预测。"
                if anomaly
                else "历史样本未显示稳定偏离；无论审计结果如何，所有合法单注仍按理论等概率生成。"
            ),
        )
        return candidates, diagnostic

    def _predict_set(
        self,
        spec: GameSpec,
        play: PlaySpec,
        draws: list[DrawRecord],
        candidate_count: int,
    ) -> tuple[list[Candidate], list[AuditResult]]:
        audits = [self._audit_matrix(self._set_matrix(draws, lane)) for lane in spec.lanes]
        signatures: set[tuple[tuple[int, ...], ...]] = set()
        candidates: list[Candidate] = []
        attempts = 0
        while len(candidates) < candidate_count and attempts < 1000:
            attempts += 1
            lanes: list[CandidateLane] = []
            signature: list[tuple[int, ...]] = []
            for lane in spec.lanes:
                ticket_count = play.ticket_size or lane.ticket_count
                numbers = tuple(
                    sorted(self.random.sample(range(1, lane.pool_size + 1), ticket_count))
                )
                signature.append(numbers)
                lanes.append(
                    CandidateLane(
                        key=lane.key,
                        label=lane.label,
                        color=lane.color,
                        numbers=[f"{number:02d}" for number in numbers],
                    )
                )
            frozen_signature = tuple(signature)
            if frozen_signature in signatures:
                continue
            signatures.add(frozen_signature)
            candidates.append(Candidate(rank=len(candidates) + 1, score_index=100.0, lanes=lanes))
        return candidates, audits

    def _predict_ordered(
        self,
        spec: GameSpec,
        play: PlaySpec,
        draws: list[DrawRecord],
        candidate_count: int,
    ) -> tuple[list[Candidate], list[AuditResult]]:
        values = np.asarray([draw.numbers[: len(spec.position_pool_sizes)] for draw in draws])
        audits = []
        for position, pool_size in enumerate(spec.position_pool_sizes):
            matrix = np.eye(pool_size, dtype=float)[values[:, position]]
            audits.append(self._audit_matrix(matrix))

        if play.id == "group3":
            population = [
                tuple(sorted((repeated, repeated, other)))
                for repeated in range(10)
                for other in range(10)
                if repeated != other
            ]
            selections = self.random.sample(population, candidate_count)
        elif play.id == "group6":
            population = list(itertools.combinations(range(10), 3))
            selections = self.random.sample(population, candidate_count)
        else:
            unique: set[tuple[int, ...]] = set()
            while len(unique) < candidate_count:
                unique.add(
                    tuple(
                        self.random.randrange(pool_size) for pool_size in spec.position_pool_sizes
                    )
                )
            selections = list(unique)

        candidates = [
            Candidate(
                rank=index + 1,
                score_index=100.0,
                lanes=[
                    CandidateLane(
                        key="digits",
                        label="号码",
                        color="violet",
                        numbers=[str(number) for number in numbers],
                    )
                ],
            )
            for index, numbers in enumerate(selections)
        ]
        return candidates, audits

    def _audit_matrix(self, matrix: np.ndarray) -> AuditResult:
        n, dimension = matrix.shape
        row_total = float(np.mean(matrix.sum(axis=1)))
        baseline_probability = row_total / dimension
        baseline = np.full(dimension, baseline_probability, dtype=float)
        possible_windows = [30, 100, 300, 1000]
        windows = sorted({min(n, window) for window in possible_windows if min(n, window) >= 20})
        evaluation_start = max(20, n - min(180, n // 3))
        anomaly_detected = False

        for window in windows:
            differences = []
            for index in range(evaluation_start, n):
                start = max(0, index - window)
                estimate = self._posterior(matrix[start:index], baseline)
                model_loss = float(np.mean((matrix[index] - estimate) ** 2))
                baseline_loss = float(np.mean((matrix[index] - baseline) ** 2))
                differences.append(baseline_loss - model_loss)
            paired = np.asarray(differences)
            if len(paired) > 2:
                mean_difference = float(np.mean(paired))
                standard_error = float(np.std(paired, ddof=1) / math.sqrt(len(paired)))
                z_score = mean_difference / standard_error if standard_error > 0 else 0.0
                # This is an audit flag only. A stricter 99% one-sided threshold reduces
                # false discoveries across multiple exploratory windows.
                anomaly_detected = anomaly_detected or (mean_difference > 0 and z_score > 2.326)

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
        return AuditResult(
            windows=windows,
            anomaly_detected=anomaly_detected,
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
