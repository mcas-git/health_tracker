"""Original short prompts informed by evidence-based habit and activity themes."""

from datetime import date

QUOTES = [
    "Small choices, repeated, become visible change.",
    "Today only asks for today's effort.",
    "Consistency carries you when motivation is quiet.",
    "A short workout still votes for the person you want to become.",
    "Progress begins again with the next choice.",
    "Train the habit and the results will follow.",
    "Your future strength is built in ordinary moments.",
    "Show up before you feel ready.",
    "A measured day is a day you can learn from.",
    "Better is enough; perfect is unnecessary.",
    "Keep promises to yourself, especially the small ones.",
    "Movement changes the mood before it changes the mirror.",
    "One honest entry is more useful than a perfect memory.",
    "The next meal is always another chance to choose well.",
    "Strength grows where excuses used to live.",
    "Do the version you can do today.",
    "Your pace is valid when it keeps you moving.",
    "Discipline is kindness sent forward to tomorrow.",
    "Every walk counts; every repetition counts; every return counts.",
    "Build a life that makes the healthy choice easier.",
    "A difficult day does not cancel a steady direction.",
    "Track without judgment, adjust with curiosity.",
    "The goal is not punishment; it is capability.",
    "Start small enough that starting feels inevitable.",
    "You do not need a new week to begin again.",
    "Recovery is part of training, not time away from it.",
    "Choose the action that your evening self will appreciate.",
    "Repeated effort is how confidence becomes evidence.",
    "Let the plan be firm and the day be flexible.",
    "The scale is one signal, never the whole story.",
    "Energy follows action more often than action follows energy.",
    "A streak is simply one more day, chosen again.",
    "Focus on the process you can repeat.",
    "Food is information, fuel and pleasure—not a moral score.",
    "The strongest routine survives imperfect days.",
    "Your body learns from what you practise consistently.",
    "Make the next useful choice, not the most dramatic one.",
    "A slow trend in the right direction is still success.",
    "Rest well enough to train with purpose.",
    "The workout starts when you decide to put on your shoes.",
    "You are allowed to improve without disliking where you began.",
    "Each check-in turns experience into a better plan.",
    "The path gets clearer after you start walking.",
    "Aim for repeatable, not remarkable.",
    "Today's effort does not have to resemble yesterday's.",
    "Use setbacks as data, not as verdicts.",
    "A good plan leaves room for being human.",
    "The body you want is built by caring for the body you have.",
    "Five focused minutes can change the direction of a day.",
    "Celebrate the behaviours that create the outcome.",
    "Patience is active when you keep doing the work.",
    "Your reasons matter more than today's resistance.",
    "Make healthy actions convenient and they become consistent.",
    "Do not wait for confidence; let action create it.",
    "There is no wasted workout and no wasted honest log.",
    "The plan works when you return to it.",
    "Move because your life deserves more energy.",
    "Enough good days will outperform a handful of perfect ones.",
    "The next milestone is hidden inside today's routine.",
    "Keep going gently, deliberately and honestly.",
]


def quote_count() -> int:
    return len(QUOTES)


def daily_item(items: list, day: date):
    """Choose one stable item for a calendar day."""
    index = day.toordinal() % len(items)
    return items[index]


def weekly_item(items: list, day: date):
    """Choose one stable item for a Monday-to-Sunday calendar week."""
    monday_ordinal = day.toordinal() - day.weekday()
    index = (monday_ordinal // 7) % len(items)
    return items[index]
