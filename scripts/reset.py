"""Reset one local demo case. No production database is touched."""

import argparse

from backend.app.config import CASES, DATA_DIR, DEMO_MODE
from backend.app.main import Registry
from backend.app.seed import reset

parser = argparse.ArgumentParser()
parser.add_argument("case", choices=CASES)
args = parser.parse_args()
if not DEMO_MODE:
    parser.error("Reset requires DEMO_MODE=true")
with Registry(DATA_DIR).get(args.case).tx() as store:
    reset(store, args.case)
print(f"Reset demo case: {args.case}")
