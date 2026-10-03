"""Explicit cost/value separation; proxy benefit, not measured welfare or probability."""

from fractions import Fraction

MODEL_VERSION = "contextual-value-v1"
SOURCES = [
    {
        "title": "Becker (1965): A Theory of the Allocation of Time",
        "url": "https://academic.oup.com/ej/article/75/299/493/5250146",
        "application": "時間投入與產出效用分開建模；演示基準不等於個人的機會成本",
    },
    {
        "title": "UK Government Analysis Function (2024): MCDA",
        "url": "https://analysisfunction.civilservice.gov.uk/policy-store/an-introductory-guide-to-mcda/",
        "application": "定義指標尺度、偏好權重、成本分列與敏感性分析；加法模型有偏好獨立假設",
    },
    {
        "title": "Nash (1950): The Bargaining Problem",
        "url": "https://www.haverford.edu/sites/default/files/Nash1950.pdf",
        "application": "在可行集合最大化雙方相對不成交的增益乘積；本版只採線性保留界限近似",
    },
]
SWINGS = {"fit": 40, "quality": 40, "quantity": 20}
OUTCOMES = {
    "spreadsheet": {
        "goal": "完成可使用的工作表",
        "observable_checks": [
            "公式與抽查資料正確",
            "交付清單完整",
            "接收者可依修改說明使用成果",
        ],
        "unmeasured": "實際節省多少時間，需另記錄原流程與使用後耗時",
    },
    "tutoring": {
        "goal": "能自行完成約定練習",
        "observable_checks": [
            "課前與課後使用相同難度的練習",
            "記錄可獨立完成的題數",
            "另記錄需要提示的程度",
        ],
        "unmeasured": "教學者歷史品質不等於接收者的學習增益；目前未量測學習前後差異",
    },
    "english": {
        "goal": "完成有回饋的口語練習",
        "observable_checks": [
            "完成約定話題與目標練習時長",
            "回饋能指向具體問題",
            "同一題型記錄練習前後的表現",
        ],
        "unmeasured": "交流時長不等於流利度改善；目前未量測長期進步",
    },
}


def recipient_benefit(
    assessment, category, target_minutes, swings=None, confirmed=False
):
    swings = swings or SWINGS
    total = sum(swings.values())
    if total <= 0 or target_minutes <= 0:
        raise ValueError("Positive swing total and target required")
    weights = {key: Fraction(swings[key], total) for key in SWINGS}
    duration_based = category != "spreadsheet"
    coverage = (
        min(Fraction(assessment["execution_minutes"], target_minutes), 1)
        if duration_based
        else Fraction(1)
    )
    components = {
        "fit": assessment["fit"],
        "quality": assessment["quality"],
        "quantity": float(100 * coverage),
    }
    valid = assessment["eligible"] and assessment["quality"] is not None
    score = (
        round(sum(float(weights[k]) * components[k] for k in weights), 2)
        if valid
        else None
    )
    # A bounded perturbation of one swing at a time exposes weight sensitivity.
    alternatives = []
    if valid:
        for key in SWINGS:
            for delta in (-10, 10):
                changed = swings | {key: max(0, min(100, swings[key] + delta))}
                if sum(changed.values()) > 0:
                    alternatives.append(
                        sum(changed[k] * components[k] for k in SWINGS)
                        / sum(changed.values())
                    )
    return {
        "model_version": MODEL_VERSION,
        "score": score,
        "scale": "0—100本單幫助指標；只供同一需求的方案比較",
        "components": components,
        "weights": {k: float(v) for k, v in weights.items()},
        "contributions": {
            k: round(float(weights[k]) * components[k], 2) for k in weights
        }
        if valid
        else None,
        "target_minutes": target_minutes if duration_based else None,
        "extra_minutes_after_target": max(
            0, assessment["execution_minutes"] - target_minutes
        )
        if duration_based
        else None,
        "quantity_basis": "min(約定服務分鐘 ÷ 目標分鐘, 1)；達到目標後停止增加此項受益"
        if duration_based
        else "完整交付約定成果的假設；不按工作時間推算成果量",
        "preference_source": "USER_CONFIRMED_SWINGS"
        if confirmed
        else "DEMO_TEMPLATE_ASSUMPTION",
        "sensitivity_range": [
            round(min(alternatives + [score]), 2),
            round(max(alternatives + [score]), 2),
        ]
        if valid
        else None,
        "sensitivity_basis": "逐項改變偏好評分±10並重新正規化；不是統計置信區間",
        "evidence_score": assessment["evidence_score"],
        "outcome_plan": OUTCOMES[category],
        "actual_outcome_measured": False,
        "limitations": "加法模型假設各指標可分開權衡；品質是相關歷史的代理量，不是成功機率。不能將分數乘上價格，也不能跨人比較幸福或公平。缺少技能或能力證據時不生成綜合分數。",
        "is_demo": True,
    }


def nash_candidates(candidates, low, high):
    """Discrete Nash-style approximation with linear reservation-bound gains."""
    best = max((x - low) * (high - x) for x in candidates)
    return sorted(x for x in candidates if (x - low) * (high - x) == best)
