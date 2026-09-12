"""Compare canonical evaluation reports without inventing ignored fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vera.evals.codec import EvalCodec
from vera.evals.contracts import EvalReport, EvalSuiteReport


@dataclass(frozen=True)
class DeterminismResult:
    equal: bool
    first: dict[str, Any]
    second: dict[str, Any]
    differences: tuple[str, ...]


class CanonicalComparator:
    def compare(
        self,
        first: EvalReport | EvalSuiteReport,
        second: EvalReport | EvalSuiteReport,
    ) -> DeterminismResult:
        if isinstance(first, EvalSuiteReport) and isinstance(second, EvalSuiteReport):
            return self._compare_suites(first, second)
        if isinstance(first, EvalReport) and isinstance(second, EvalReport):
            left = EvalCodec.canonical_report(first)
            right = EvalCodec.canonical_report(second)
            differences = tuple(_diff(left, right))
            return DeterminismResult(
                equal=not differences,
                first=left,
                second=right,
                differences=differences,
            )
        raise TypeError("canonical comparison requires matching report types")

    def _compare_suites(self, first: EvalSuiteReport, second: EvalSuiteReport) -> DeterminismResult:
        first_ids = {item.case_id for item in first.cases}
        second_ids = {item.case_id for item in second.cases}
        differences: list[str] = []
        for case_id in sorted(first_ids - second_ids):
            differences.append(f"missing:{case_id}")
        for case_id in sorted(second_ids - first_ids):
            differences.append(f"extra:{case_id}")
        projections: dict[str, Any] = {"cases": []}
        other: dict[str, Any] = {"cases": []}
        for case_id in sorted(first_ids & second_ids):
            result = self.compare(first.case(case_id), second.case(case_id))
            projections["cases"].append(result.first)
            other["cases"].append(result.second)
            differences.extend(f"{case_id}:{path}" for path in result.differences)
        return DeterminismResult(
            equal=not differences,
            first=projections,
            second=other,
            differences=tuple(differences),
        )


def _diff(left: Any, right: Any, path: str = "") -> list[str]:
    if left == right:
        return []
    if type(left) is not type(right):
        return [path or "root"]
    if isinstance(left, dict):
        differences: list[str] = []
        keys = sorted(set(left) | set(right))
        for key in keys:
            child = f"{path}.{key}" if path else key
            if key not in left or key not in right:
                differences.append(child)
            else:
                differences.extend(_diff(left[key], right[key], child))
        return differences
    if isinstance(left, list):
        if len(left) != len(right):
            return [path or "root"]
        differences = []
        for index, (first_item, second_item) in enumerate(zip(left, right, strict=True)):
            child = f"{path}[{index}]" if path else f"[{index}]"
            differences.extend(_diff(first_item, second_item, child))
        return differences
    return [path or "root"]
