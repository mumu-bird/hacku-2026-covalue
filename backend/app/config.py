import os
from pathlib import Path

RULE_VERSION = "time-value-v0.3"
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
DATA_DIR = Path(os.getenv("HOURLINK_DATA_DIR", "backend/data"))
CASES = {
    "cash": "付費成功",
    "no_deal": "沒有可行方案",
    "withdrawal": "部分履約後退出",
    "barter": "時間互換",
    "hybrid": "互換補差",
}
POLICY = {
    "currency": "HKD",
    "amount_step": 100,
    "time_step": 15,
    "default_capacity": 1,
    "advanced_capacity": 2,
    "advance_minutes": 30,
    "advanced_minutes": 60,
    "response_hours": 24,
    "initial_balance": 100000,
    "quality_weights": [50, 30, 20],
    "ranking_weights": [60, 30, 10],
    "sufficient_orders": 3,
    "max_evidence": 20,
    "max_external": 2,
}
TEMPLATES = {
    "spreadsheet": {
        "name": "表格處理",
        "basis": "DELIVERABLE",
        "base_rate": 20000,
        "minutes": {"small": 30, "medium": 60, "large": 120},
        "skills": ["資料清理", "公式", "格式整理"],
        "rubric": ["資料與公式正確", "完整符合交付清單", "能獨立處理例外"],
        "deliverable": "整理後的工作表與修改說明",
    },
    "tutoring": {
        "name": "表格輔導",
        "basis": "DURATION",
        "base_rate": 10000,
        "minutes": {"small": 30, "medium": 60, "large": 90},
        "skills": ["公式", "教學", "資料清理"],
        "rubric": ["示範與解釋正確", "完成約定教學內容", "獨立解答練習問題"],
        "deliverable": "約定時長的輔導與練習回饋",
    },
    "english": {
        "name": "英語交流",
        "basis": "DURATION",
        "base_rate": 10000,
        "minutes": {"small": 30, "medium": 60, "large": 90},
        "skills": ["英語交流", "口語回饋", "教學"],
        "rubric": ["回饋與表達準確", "完成約定交流內容", "能獨立引導對話"],
        "deliverable": "約定時長的交流與回饋",
    },
}
