"""Gemini usage logging, cost estimates and the monthly budget."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from . import db
from .errors import UserError

WARN_AT = 0.8


class BudgetExceeded(UserError):
    def __init__(self, spent: float, budget: float) -> None:
        super().__init__(
            f"Monthly AI budget reached (${spent:.2f} of ${budget:.2f}). "
            "Premium generation is blocked until next month or until an admin raises the budget."
        )


@dataclass
class Price:
    input_per_mtok: float = 0
    output_per_mtok: float = 0
    audio_out_per_mtok: float = 0
    per_image: float = 0
    per_video_second: float = 0


def price_for(model: str) -> Price:
    name = model.removeprefix("models/")
    row = db.fetch_one(
        "select * from model_pricing where %s like model || '%%' order by length(model) desc limit 1", [name]
    )
    if not row:
        return Price()
    return Price(**{k: float(row[k]) for k in Price.__dataclass_fields__})


def estimate_cost(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    images: int = 0,
    seconds: float = 0,
    audio_output: bool = False,
) -> float:
    p = price_for(model)
    out_rate = p.audio_out_per_mtok if audio_output and p.audio_out_per_mtok else p.output_per_mtok
    return (
        input_tokens / 1e6 * p.input_per_mtok
        + output_tokens / 1e6 * out_rate
        + images * p.per_image
        + seconds * p.per_video_second
    )


def record(
    *,
    model: str,
    kind: str,
    user_id: UUID | str | None = None,
    project_id: UUID | str | None = None,
    job_id: UUID | str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    images: int = 0,
    seconds: float = 0,
    meta: dict[str, Any] | None = None,
) -> float:
    cost = estimate_cost(
        model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        images=images,
        seconds=seconds,
        audio_output=(kind == "tts"),
    )
    db.execute(
        """insert into usage_events (model, kind, user_id, project_id, job_id, input_tokens, output_tokens,
                                     images, seconds, cost_usd, meta)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        [
            model.removeprefix("models/"),
            kind,
            user_id,
            project_id,
            job_id,
            input_tokens,
            output_tokens,
            images,
            Decimal(str(round(seconds, 2))),
            Decimal(str(round(cost, 6))),
            meta or {},
        ],
    )
    return cost


def month_spend() -> float:
    row = db.fetch_one(
        "select coalesce(sum(cost_usd), 0) as s from usage_events where ts >= date_trunc('month', now())"
    )
    return float(row["s"]) if row else 0.0


def budget_state() -> dict[str, Any]:
    row = db.fetch_one("select monthly_budget_usd from settings where id = 1")
    budget = float(row["monthly_budget_usd"]) if row and row["monthly_budget_usd"] is not None else None
    spent = month_spend()
    if not budget:
        return {"budget": None, "spent": spent, "ratio": 0.0, "level": "ok"}
    ratio = spent / budget
    level = "blocked" if ratio >= 1 else "warn" if ratio >= WARN_AT else "ok"
    return {"budget": budget, "spent": spent, "ratio": ratio, "level": level}


def premium_allowed() -> bool:
    return budget_state()["level"] != "blocked"


def assert_premium_allowed() -> None:
    st = budget_state()
    if st["level"] == "blocked":
        raise BudgetExceeded(st["spent"], st["budget"])
