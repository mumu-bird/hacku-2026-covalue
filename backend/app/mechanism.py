"""Synthetic experiments execute the production evaluator and solver in isolated databases."""

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from . import domain as d
from .config import RULE_VERSION
from .db import DB, dump
from .seed import seed
from .value_model import MODEL_VERSION, SOURCES, recipient_benefit


def simulate_value(inputs):
    with TemporaryDirectory(prefix="hourlink-value-") as folder:
        db = DB(Path(folder) / "experiment.sqlite3")
        try:
            with db.tx() as s:
                seed(s, "barter")
                s.execute(
                    "UPDATE evidence SET quality=? WHERE owner_id='zao' AND category='english'",
                    (inputs["quality"],),
                )
                listing = d.get(s, "listings", "offer-zao-english")
                task = listing["data"] | {
                    "category": "english",
                    "duration": inputs["received_minutes"],
                    "required_skills": ["英語交流", "口語回饋"],
                }
                reference = d.evaluate(s, "zao", task)
                benefit = recipient_benefit(
                    reference,
                    "english",
                    inputs["target_minutes"],
                    {k: inputs[f"swing_{k}"] for k in ("fit", "quality", "quantity")},
                )
                benefit["preference_source"] = "SYNTHETIC_EXPERIMENT"
                return {
                    "inputs": inputs,
                    "reference": reference["value_estimate"],
                    "benefit": benefit,
                    "is_demo": True,
                }
        finally:
            db.engine.dispose()


VALUE_DEFAULTS = {
    "received_minutes": 90,
    "target_minutes": 60,
    "quality": 74,
    "swing_fit": 40,
    "swing_quality": 40,
    "swing_quantity": 20,
}


def value_report():
    return {
        "model_version": MODEL_VERSION,
        "sources": SOURCES,
        "is_demo": True,
        "experiments": [
            simulate_value(VALUE_DEFAULTS | {"received_minutes": minutes})
            for minutes in (30, 60, 90, 120)
        ],
        "method": "相同能力與目標，改變服務分鐘。使用正式評估、受益模型和隔離SQLite；不是用戶研究。",
    }


def simulate(inputs):
    with TemporaryDirectory(prefix="hourlink-mechanism-") as folder:
        db = DB(Path(folder) / "experiment.sqlite3")
        try:
            with db.tx() as s:
                seed(s, "barter")
                p = d.get(s, "proposals", s.one("SELECT id FROM proposals")["id"])
                data = p["data"]
                scope = data["scope"]
                scope.update(
                    duration=inputs["main_minutes"],
                    preparation=inputs["preparation"],
                    include_preparation=True,
                )
                scope["end"] = (
                    d.instant(scope["start"])
                    + timedelta(minutes=inputs["window_minutes"])
                ).isoformat()
                data["recommendation"] = None
                s.execute(
                    "UPDATE evidence SET quality=? WHERE owner_id='lin' AND category='tutoring'",
                    (inputs["quality"],),
                )
                if inputs["evidence_mode"] == "MISSING":
                    s.execute(
                        "DELETE FROM evidence WHERE owner_id='lin' AND category='tutoring'"
                    )
                    scope["required_skills"] = []
                    scope["preferred_skills"] = []
                s.execute(
                    "UPDATE proposals SET data=?,path='ASSISTED' WHERE id=?",
                    (dump(data), p["id"]),
                )
                p = d.get(s, "proposals", p["id"])
                main = d.evaluate(s, "lin", scope)
                equal_time = d.evaluate(
                    s, "zao", data["reverse"] | {"duration": inputs["main_minutes"]}
                )
                result = {
                    "inputs": inputs,
                    "is_demo": True,
                    "rule_version": RULE_VERSION,
                    "main": main,
                    "equal_time_gap": abs(
                        main["total_amount"] - equal_time["total_amount"]
                    ),
                    "recommendation": None,
                    "negotiation": None,
                    "status": "ADVICE_AVAILABLE",
                    "failure": None,
                }
                try:
                    result["recommendation"] = d.recommendation(s, p)
                    rec = result["recommendation"]
                    result["reference_gap"] = abs(
                        rec["main"]["total_amount"] - rec["reverse"]["total_amount"]
                    )
                    result["service_acceptances"] = 2 * rec["rounds"]
                    result["workflow_commands"] = 2 + 4 * rec["rounds"]
                    for user, value in [
                        ("lin", inputs["lower"]),
                        ("zao", inputs["upper"]),
                    ]:
                        d.preference(
                            s,
                            user,
                            p,
                            {
                                "expected_version": p["version"],
                                "scope_version": p["scope_version"],
                                "value": value,
                            },
                        )
                    result["negotiation"] = d.calculate(s, "zao", p, p["version"])
                    result["status"] = "ACCEPTABLE_CANDIDATE"
                except d.DomainError as error:
                    result["failure"] = error.payload()
                    result["status"] = (
                        "NO_DEAL"
                        if error.code == "NO_FEASIBLE_PLAN"
                        else "REVIEW_REQUIRED"
                    )
                return result
        finally:
            db.engine.dispose()


DEFAULTS = {
    "quality": 90,
    "main_minutes": 60,
    "preparation": 0,
    "window_minutes": 240,
    "lower": 60,
    "upper": 120,
    "evidence_mode": "VERIFIED",
}


@lru_cache(maxsize=1)
def report():
    experiments = []
    for key, values in [
        ("quality", [59, 60, 79, 80, 89, 90]),
        ("preparation", [0, 10, 20, 31]),
        ("window_minutes", [60, 90, 120, 150]),
    ]:
        for value in values:
            experiments.append(
                {
                    "group": key,
                    "label": f"{key}={value}",
                    **simulate(DEFAULTS | {key: value}),
                }
            )
    for low, high in [(90, 60), (60, 60), (75, 120)]:
        experiments.append(
            {
                "group": "acceptance",
                "label": f"{low}..{high}",
                **simulate(DEFAULTS | {"lower": low, "upper": high}),
            }
        )
    experiments.append(
        {
            "group": "evidence",
            "label": "No verified evidence",
            **simulate(DEFAULTS | {"evidence_mode": "MISSING"}),
        }
    )
    main = {
        "estimated_minutes": 120,
        "execution_minutes": 120,
        "preparation_minutes": 0,
        "travel_minutes": 0,
    }
    reverse = {"preparation_minutes": 0, "travel_minutes": 0}
    tradeoffs = []
    for limit in [30, 60]:
        rounds = d.exchange_rounds(main, reverse, 180, 360, limit)
        tradeoffs.append(
            {
                "first_investment_limit": limit,
                "rounds": rounds,
                "first_unreturned_minutes": 120 // rounds,
                "service_acceptances": 2 * rounds,
                "workflow_commands": 2 + 4 * rounds,
            }
        )
    return {
        "is_demo": True,
        "rule_version": RULE_VERSION,
        "experiments": experiments,
        "tradeoffs": tradeoffs,
        "method": "Production rules, isolated seeded SQLite; controlled synthetic inputs; no real-user success or economic fairness claim.",
        "command_count_basis": "Barter: 2 signatures + 2 services per round × (submission + acceptance). Excludes setup, scheduling, exit and review; not elapsed time.",
        "limitations": [
            "Quality coefficients jump at 80 and 90; these boundaries require calibration.",
            "A smaller reference gap does not imply both parties want the deal.",
            "More rounds reduce first unreturned service but add acceptance actions.",
            "No verified capability pauses definite platform advice; newcomers need a reviewed work or assessment.",
            "Indivisible work or preparation exceeding the first-investment limit cannot use the current staged barter rule.",
        ],
    }
