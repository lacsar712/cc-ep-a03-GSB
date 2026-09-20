"""双 Run 对照的纯函数 diff 逻辑(不依赖 DB,便于单测)。"""

from __future__ import annotations

from typing import Any

from app.models import RunProjection


def latest_metrics_by_name(metrics: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """把指标流水按 name 归并,保留 step 最大的那条(并列时取后记录的)。"""
    latest: dict[str, dict[str, Any]] = {}
    for m in metrics or []:
        name = m.get("name")
        if not name:
            continue
        prev = latest.get(name)
        if prev is None or m.get("step", 0) >= prev.get("step", 0):
            latest[name] = m
    return latest


def build_compare_diff(proj_a: RunProjection, proj_b: RunProjection) -> dict[str, Any]:
    """对两条 Run 投影做对照:指纹是否一致、指标名差集、同名指标最新值差异。"""
    latest_a = latest_metrics_by_name(proj_a.metrics_json)
    latest_b = latest_metrics_by_name(proj_b.metrics_json)
    names_a = set(latest_a)
    names_b = set(latest_b)

    rows: list[dict[str, Any]] = []
    for name in sorted(names_a | names_b):
        ma = latest_a.get(name)
        mb = latest_b.get(name)
        rows.append(
            {
                "name": name,
                "in_a": ma is not None,
                "in_b": mb is not None,
                "a_value": ma.get("value") if ma else None,
                "a_step": ma.get("step") if ma else None,
                "b_value": mb.get("value") if mb else None,
                "b_step": mb.get("step") if mb else None,
                "value_differs": bool(ma and mb and ma.get("value") != mb.get("value")),
            }
        )

    return {
        "code_commit_same": proj_a.code_commit_sha.lower() == proj_b.code_commit_sha.lower(),
        "dataset_same": proj_a.dataset_content_sha256.lower()
        == proj_b.dataset_content_sha256.lower(),
        "metric_names_only_a": sorted(names_a - names_b),
        "metric_names_only_b": sorted(names_b - names_a),
        "metrics": rows,
    }
