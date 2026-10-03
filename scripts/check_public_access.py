"""Check unauthenticated submission links and report the remote revision observed."""

import json
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

repo = "mumu-bird/hacku-2026-covalue"
headers = {"User-Agent": "Hourlink-public-submission-check"}


def fetch(url, method="GET"):
    # No authorization header, cookies, GitHub CLI authentication or browser session.
    with urlopen(Request(url, headers=headers, method=method), timeout=30) as response:
        assert response.status == 200, (url, response.status)
        return response.read() if method == "GET" else None


meta = json.loads(fetch(f"https://api.github.com/repos/{repo}"))
assert not meta["private"], "Official submission requires a public repository"
commit = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits/main"))["sha"]
items = [
    ("Repository", f"https://github.com/{repo}"),
    ("Setup instructions", f"https://raw.githubusercontent.com/{repo}/main/README.md"),
    (
        "Recorded demo",
        f"https://raw.githubusercontent.com/{repo}/main/artifacts/hourlink-demo.webm",
    ),
    (
        "Pitch PDF",
        f"https://raw.githubusercontent.com/{repo}/main/output/pdf/hourlink-pitch.pdf",
    ),
    (
        "Mechanism evidence",
        f"https://raw.githubusercontent.com/{repo}/main/docs/mechanism-results.json",
    ),
    (
        "Competitive sources",
        f"https://raw.githubusercontent.com/{repo}/main/docs/competitive-comparison.md",
    ),
]
for label, url in items:
    fetch(url, "HEAD")
    print("PUBLIC 200", label)
stamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
text = f"# Public submission access check\n\nChecked {stamp} without authentication or cookies. Repository is PUBLIC. Observed main revision: `{commit}`.\n\n| Material | Anonymous access |\n|---|---|\n"
text += "".join(f"| [{label}]({url}) | HTTP 200 |\n" for label, url in items)
text += "\nThis verifies access, not official form submission, judging eligibility, real payments or user-study completion. Real participant feedback is still awaiting collection; see research/README.md.\n"
Path("docs/public-access-report.md").write_text(text)
print("Verified public materials at", commit)
