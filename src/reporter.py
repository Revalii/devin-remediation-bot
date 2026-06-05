from pathlib import Path
from typing import Any
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_FILE = PROJECT_ROOT / "reports" / "remediation_report.md"


def generate_report(sessions: dict[str, Any]) -> str:
    """
    Generate a lightweight Markdown report for engineering leaders.
    """
    total_sessions = len(sessions)

    status_counts: dict[str, int] = {}

    for session in sessions.values():
        status = session.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    simulated = status_counts.get("simulated", 0)
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    running = status_counts.get("running", 0)

    generated_at = datetime.now(timezone.utc).isoformat()

    lines = [
        "# Devin Remediation Report",
        "",
        f"Generated at: `{generated_at}`",
        "",
        "## Summary",
        "",
        f"- Total sessions tracked: {total_sessions}",
        f"- Simulated sessions: {simulated}",
        f"- Running sessions: {running}",
        f"- Completed sessions: {completed}",
        f"- Failed sessions: {failed}",
        "",
        "## Task Details",
        "",
        "| Issue | Title | Status | Detail | Session ID | PR | Issue URL |",
        "|---|---|---|---|---|---|---|",
    ]

    for issue_number, session in sorted(
            sessions.items(), key=lambda item: int(item[0])
    ):
        title = session.get("issue_title", "")
        status = session.get("status", "unknown")
        session_id = session.get("session_id", "")
        issue_url = session.get("issue_url", "")

        raw_status = session.get("raw_status", {})
        status_detail = raw_status.get("status_detail", "")

        pull_requests = session.get("pull_requests", [])
        pr_url = ""

        if pull_requests:
            pr_url = pull_requests[0].get("pr_url", "")

        pr_display = f"[PR]({pr_url})" if pr_url else "N/A"

        lines.append(
            f"| #{issue_number} | {title} | {status} | {status_detail} | `{session_id}` | {pr_display} | [Issue]({issue_url}) |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This report shows which labelled GitHub issues were picked up by the automation and converted into Devin session records.",
            "",
            "In dry-run mode, sessions are simulated to validate the workflow safely before calling the real Devin API.",
            "",
            "In production mode, these session records would be updated with real Devin session IDs, pull request URLs, completion status, and failure signals.",
            "",
            "## Human Review Boundary",
            "",
            "The automation is designed to create reviewable pull requests, not to merge code automatically. Human review remains required before any change is merged.",
        ]
    )

    return "\n".join(lines)


def save_report(report: str) -> None:
    """
    Save the Markdown report to reports/remediation_report.md.
    """
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with REPORT_FILE.open("w", encoding="utf-8") as file:
        file.write(report)
