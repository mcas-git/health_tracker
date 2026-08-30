from __future__ import annotations

import json
from datetime import date
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select

from health_tracker.config import setting
from health_tracker.db import session_scope
from health_tracker.models import NutritionLog


class MealEstimate(BaseModel):
    label: str = Field(min_length=1, description="Inferred meal label or approximate time")
    foods: list[str] = Field(min_length=1)
    calories: int = Field(ge=0, le=15_000)
    protein_g: float = Field(ge=0, le=1_000)
    carbs_g: float = Field(ge=0, le=1_000)
    fat_g: float = Field(ge=0, le=1_000)
    fibre_g: float = Field(ge=0, le=1_000)


class DailyNutritionEstimate(BaseModel):
    meals: list[MealEstimate] = Field(min_length=1)
    summary: str = Field(description="Short summary including important serving assumptions")
    calories: int = Field(ge=0, le=15_000)
    protein_g: float = Field(ge=0, le=1_000)
    carbs_g: float = Field(ge=0, le=1_000)
    fat_g: float = Field(ge=0, le=1_000)
    fibre_g: float = Field(ge=0, le=1_000)
    confidence: Literal["low", "medium", "high"]


SYSTEM_PROMPT = """You estimate calories and macronutrients from one person's informal full-day
food note in a UK setting.

UK interpretation rules:
- Use UK English and UK foods. For example, "chips" means hot potato chips and "crisps" means the
  packaged snack. Prefer typical UK portions and the UK Composition of Foods Integrated Dataset
  (CoFID) when a food has no label or stated quantity.
- Treat a stated packet, restaurant, or recipe nutrition value as more authoritative than a generic
  food estimate. Values explicitly stated per serving should be used directly. Values per 100 g or
  100 ml must be scaled to the amount actually eaten or drunk.
- Report energy as kcal. If only kJ is supplied, convert using 1 kcal = 4.184 kJ.
- Follow UK label conventions: carbohydrate is available carbohydrate and does not include fibre.
  Keep fibre separate. For a reasonableness check, carbohydrate and protein contribute 4 kcal/g,
  fat 9 kcal/g, and fibre 2 kcal/g. Alcohol contributes 7 kcal/g when relevant.
- Include every mentioned meal, drink, snack, sauce, cooking oil, spread, milk in tea or coffee,
  and alcoholic drink. Do not invent an omitted item.
- When quantities are missing, make one realistic point estimate rather than a range and state the
  important portion assumptions in the summary. Lower confidence when portions or preparation are
  materially ambiguous.

Split the note into meals or eating occasions. Totals must equal the arithmetic sum of the meal
estimates. Round calories to whole kcal and macros to one decimal place. Do not provide medical
advice. Keep the summary short.

UK label reference checks:
1. Two slices where each slice states 105 kcal, 3.4 g protein, 20.0 g carbohydrate, 0.7 g fat and
   1.2 g fibre total 210 kcal, 6.8 g protein, 40.0 g carbohydrate, 1.4 g fat and 2.4 g fibre.
2. A whole 400 g meal labelled per 100 g as 125 kcal, 6 g protein, 15 g carbohydrate, 4 g fat and
   2 g fibre totals 500 kcal, 24 g protein, 60 g carbohydrate, 16 g fat and 8 g fibre."""


def quality_assure_estimate(estimate: DailyNutritionEstimate) -> DailyNutritionEstimate:
    """Make persisted day totals the deterministic sum of the extracted meals."""
    totals = {
        "calories": sum(meal.calories for meal in estimate.meals),
        "protein_g": round(sum(meal.protein_g for meal in estimate.meals), 1),
        "carbs_g": round(sum(meal.carbs_g for meal in estimate.meals), 1),
        "fat_g": round(sum(meal.fat_g for meal in estimate.meals), 1),
        "fibre_g": round(sum(meal.fibre_g for meal in estimate.meals), 1),
    }
    return estimate.model_copy(update=totals)


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
    return quality_assure_estimate(response.output_parsed), model


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
