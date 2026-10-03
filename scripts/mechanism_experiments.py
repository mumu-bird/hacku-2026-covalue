"""Export reproducible mechanism evidence for the competition materials."""

import json
from pathlib import Path

from backend.app.mechanism import report

result = report()
Path("docs/mechanism-results.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n"
)
print(
    f"Exported {len(result['experiments'])} controlled experiments and {len(result['tradeoffs'])} trade-offs."
)
