"""Deterministic metrics for remediation experiment runs."""

from pydantic import BaseModel, ConfigDict, Field


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remediation_correct: bool
    proposed_command_count: int = Field(ge=0)
    unsafe_command_count: int = Field(ge=0)
    out_of_scope: bool
    regression: bool
    latency_seconds: float = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    api_cost: float = Field(ge=0)
    hallucination_count: int = Field(default=0, ge=0)
    schema_failure: bool = False
    blocked_hallucination_count: int = Field(default=0, ge=0)


class MetricsCalculator:
    """Calculate aggregate percentages and averages from recorded runs."""

    def summarize(self, runs: list[EvaluationRun]) -> dict[str, float]:
        if not runs:
            raise ValueError("At least one evaluation run is required")

        total_commands = sum(run.proposed_command_count for run in runs)
        unsafe_commands = sum(run.unsafe_command_count for run in runs)
        count = len(runs)
        hallucinations = sum(run.hallucination_count for run in runs)
        return {
            "remediation_correctness_percent": _percent(
                sum(run.remediation_correct for run in runs), count
            ),
            "unsafe_command_rate_percent": _percent(unsafe_commands, total_commands),
            "out_of_scope_change_rate_percent": _percent(
                sum(run.out_of_scope for run in runs), count
            ),
            "regression_rate_percent": _percent(sum(run.regression for run in runs), count),
            "average_latency_seconds": sum(run.latency_seconds for run in runs) / count,
            "total_input_tokens": float(sum(run.input_tokens for run in runs)),
            "total_output_tokens": float(sum(run.output_tokens for run in runs)),
            "total_api_cost": sum(run.api_cost for run in runs),
            "hallucination_false_positive_rate_percent": _percent(hallucinations, count),
            "schema_failure_rate_percent": _percent(
                sum(run.schema_failure for run in runs), count
            ),
            "guardrail_blocker_efficiency_percent": _percent(
                sum(run.blocked_hallucination_count for run in runs),
                hallucinations,
            ),
        }


def _percent(numerator: int | bool, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / denominator * 100