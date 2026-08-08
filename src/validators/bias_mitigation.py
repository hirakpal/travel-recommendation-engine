"""Reusable bias checks for recommendation results.

The helpers in this module are provider-agnostic. They can be used after an
agent has produced recommendations and before results are returned to a user.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence


@dataclass
class BiasFinding:
    """A single bias or integrity finding."""

    check: str
    message: str
    severity: str = "warning"


@dataclass
class BiasReport:
    """Result of running bias and integrity checks."""

    passed: bool
    findings: list[BiasFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[BiasFinding]:
        """Return findings that should block a recommendation response."""

        return [finding for finding in self.findings if finding.severity == "error"]


def _value(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a mapping or an object."""

    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


class BiasMitigator:
    """Run deterministic checks against recommendation candidates."""

    def __init__(self, score_tolerance: float = 0.15):
        self.score_tolerance = score_tolerance

    def check_anchor_bias(
        self,
        recommendations: Sequence[Any],
        score_key: str = "match_score",
    ) -> BiasFinding | None:
        """Detect a first-result score advantage not supported by the data."""

        if len(recommendations) < 2:
            return None

        first_score = _value(recommendations[0], score_key)
        other_scores = [
            _value(item, score_key)
            for item in recommendations[1:]
        ]
        other_scores = [score for score in other_scores if isinstance(score, (int, float))]

        if not isinstance(first_score, (int, float)) or not other_scores:
            return None

        average_score = sum(other_scores) / len(other_scores)
        if first_score - average_score > self.score_tolerance:
            return BiasFinding(
                check="anchor_bias",
                message="The first recommendation is scored materially above the remaining results.",
            )

        return None

    def check_hallucinations(
        self,
        recommendations: Iterable[Any],
        candidates: Iterable[Any],
        id_key: str = "id",
    ) -> BiasFinding | None:
        """Ensure every recommended item came from the supplied candidates."""

        candidate_ids = {
            _value(candidate, id_key)
            for candidate in candidates
        }
        recommended_ids = {
            _value(recommendation, id_key)
            for recommendation in recommendations
        }
        recommended_ids.discard(None)

        unknown_ids = recommended_ids - candidate_ids
        if unknown_ids:
            return BiasFinding(
                check="hallucination",
                message=f"Recommendations contain unknown candidate IDs: {sorted(unknown_ids)}.",
                severity="error",
            )

        return None

    def check_constraints(
        self,
        recommendations: Iterable[Any],
        predicate: Callable[[Any], bool],
        description: str = "recommendation constraints",
    ) -> BiasFinding | None:
        """Ensure all recommendations satisfy a caller-provided predicate."""

        invalid_count = sum(1 for item in recommendations if not predicate(item))
        if invalid_count:
            return BiasFinding(
                check="constraint_compliance",
                message=f"{invalid_count} recommendation(s) failed {description}.",
                severity="error",
            )

        return None

    def check_diversity(
        self,
        recommendations: Sequence[Any],
        category_key: str,
        minimum_categories: int = 2,
    ) -> BiasFinding | None:
        """Detect results that over-concentrate in one category."""

        categories = {
            _value(item, category_key)
            for item in recommendations
        }
        categories.discard(None)

        if len(recommendations) > 1 and len(categories) < minimum_categories:
            return BiasFinding(
                check="lack_of_diversity",
                message=f"Results contain fewer than {minimum_categories} categories.",
            )

        return None

    def run(
        self,
        recommendations: Sequence[Any],
        candidates: Sequence[Any] | None = None,
        score_key: str = "match_score",
        id_key: str = "id",
        category_key: str | None = None,
        constraint: Callable[[Any], bool] | None = None,
        constraint_description: str = "recommendation constraints",
    ) -> BiasReport:
        """Run all requested checks and return a structured report."""

        findings: list[BiasFinding] = []

        checks = [
            self.check_anchor_bias(recommendations, score_key),
        ]

        if candidates is not None:
            checks.append(
                self.check_hallucinations(
                    recommendations,
                    candidates,
                    id_key,
                )
            )

        if category_key is not None:
            checks.append(
                self.check_diversity(
                    recommendations,
                    category_key,
                )
            )

        if constraint is not None:
            checks.append(
                self.check_constraints(
                    recommendations,
                    constraint,
                    constraint_description,
                )
            )

        findings.extend(finding for finding in checks if finding is not None)

        return BiasReport(
            passed=not any(finding.severity == "error" for finding in findings),
            findings=findings,
        )


def validate_recommendations(
    recommendations: Sequence[Any],
    candidates: Sequence[Any] | None = None,
    **kwargs: Any,
) -> BiasReport:
    """Convenience wrapper for one-off validation."""

    return BiasMitigator().run(
        recommendations=recommendations,
        candidates=candidates,
        **kwargs,
    )

