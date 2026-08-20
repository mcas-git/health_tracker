from __future__ import annotations

import json
from datetime import date

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select

from health_tracker.config import setting
from health_tracker.db import session_scope
from health_tracker.models import NutritionLog


class MealEstimate(BaseModel):
    label: str = Field(description="Inferred meal label or approximate time")
    foods: list[str]
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    fibre_g: float


class DailyNutritionEstimate(BaseModel):
    meals: list[MealEstimate]
    summary: str = Field(description="Short summary including important serving assumptions")
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    fibre_g: float
    confidence: str = Field(description="One of low, medium, high")


SYSTEM_PROMPT = """You estimate nutrition from one person's informal full-day food note.
Split the note intuitively into meals or eating occasions. Use typical UK serving sizes when
quantities are absent. Include drinks, sauces, oils, and snacks when mentioned. Return realistic
point estimates, not ranges. Totals must equal the sum of meal estimates. Do not provide medical
advice. Keep the summary short and state the most important assumptions."""


def analyse_day(note: str) -> tuple[DailyNutritionEstimate, str]:
    model = setting("OPENAI_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=setting("OPENAI_API_KEY"))
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": note},
        ],
        text_format=DailyNutritionEstimate,
    )
    if response.output_parsed is None:
        raise ValueError("The nutrition response could not be parsed.")
    return response.output_parsed, model


def save_estimate(entry_date: date, note: str, estimate: DailyNutritionEstimate, model: str):
    with session_scope() as session:
        item = session.scalar(select(NutritionLog).where(NutritionLog.entry_date == entry_date))
        if item is None:
            item = NutritionLog(entry_date=entry_date, raw_note=note)
            session.add(item)
        item.raw_note = note
        item.meals_json = json.dumps([meal.model_dump() for meal in estimate.meals])
        item.summary = estimate.summary
        item.calories = estimate.calories
        item.protein_g = estimate.protein_g
        item.carbs_g = estimate.carbs_g
        item.fat_g = estimate.fat_g
        item.fibre_g = estimate.fibre_g
        item.confidence = estimate.confidence.lower()
        item.model = model
