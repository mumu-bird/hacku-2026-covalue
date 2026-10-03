"""Export reproducible mechanism evidence for the competition materials."""

import json
from pathlib import Path

from backend.app.mechanism import report, value_report

result = report()
Path("docs/mechanism-results.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n"
)
print(
    f"Exported {len(result['experiments'])} controlled experiments and {len(result['tradeoffs'])} trade-offs."
)
values = value_report()
Path("docs/value-model-results.json").write_text(
    json.dumps(values, ensure_ascii=False, indent=2) + "\n"
)
print(f"Exported {len(values['experiments'])} contextual value experiments.")
