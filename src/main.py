import os
import requests
from dotenv import load_dotenv

from src.session_store import load_sessions
from src.remediation import (
    process_issue,
    refresh_live_sessions,
    finalize_sessions_with_prs,
    save_state_and_report,
)


def get_open_issues(owner: str, repo: str, github_token: str | None = None) -> list[dict]:
    """
    Fetch open GitHub issues from the target repository.

    GitHub's issues API can return both issues and pull requests.
    Pull requests are filtered out later by checking whether 'pull_request' exists.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"

    headers = {
        "Accept": "application/vnd.github+json",
    }

    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    params = {
        "state": "open",
        "per_page": 100,
    }

    response = requests.get(url, headers=headers, params=params, timeout=20)

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub API request failed: {response.status_code} {response.text}"
        )

    return response.json()


def has_label(issue: dict, target_label: str) -> bool:
    """
    Check whether a GitHub issue has the target label.
    """
    labels = issue.get("labels", [])

    for label in labels:
        if label.get("name") == target_label:
            return True

    return False


def get_issue_label_names(issue: dict) -> set[str]:
    """
    Return all label names on a GitHub issue.
    """
    return {
        label.get("name", "")
        for label in issue.get("labels", [])
        if label.get("name")
    }


def parse_allowed_task_labels(raw_labels: str) -> set[str]:
    """
    Parse comma-separated allowed task labels from the environment.
    """
    return {
        label.strip()
        for label in raw_labels.split(",")
        if label.strip()
    }


def has_allowed_task_label(issue: dict, allowed_labels: set[str]) -> bool:
    """
    Check whether an issue has at least one allowed low-risk task label.
    """
    if not allowed_labels:
        return True

    issue_labels = get_issue_label_names(issue)
    return bool(issue_labels.intersection(allowed_labels))


def main() -> None:
    load_dotenv()

    owner = os.getenv("GITHUB_OWNER", "Revalii")
    repo = os.getenv("GITHUB_REPO", "superset")
    target_label = os.getenv("TARGET_LABEL", "devin-remediate")
    target_issue_number = os.getenv("TARGET_ISSUE_NUMBER")
    allowed_task_labels = parse_allowed_task_labels(
        os.getenv("ALLOWED_TASK_LABELS", "")
    )

    github_token = os.getenv("GITHUB_TOKEN") or None

    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    devin_org_id = os.getenv("DEVIN_ORG_ID") or ""
    devin_api_key = os.getenv("DEVIN_API_KEY") or ""

    print(f"Allowed task labels: {sorted(allowed_task_labels) if allowed_task_labels else 'not restricted'}")
    print(f"Scanning repository: {owner}/{repo}")
    print(f"Target label: {target_label}")
    print(f"DRY_RUN: {dry_run}")
    print("-" * 60)

    issues = get_open_issues(owner, repo, github_token)

    matched_issues = []

    for issue in issues:
        if "pull_request" in issue:
            continue

        if has_label(issue, target_label):
            if not has_allowed_task_label(issue, allowed_task_labels):
                print(
                    f"Skipping issue #{issue['number']}: missing allowed task label "
                    f"{sorted(allowed_task_labels)}"
                )
                continue

            matched_issues.append(issue)

    if target_issue_number:
        matched_issues = [
            issue for issue in matched_issues
            if str(issue["number"]) == target_issue_number
        ]

        print(f"TARGET_ISSUE_NUMBER={target_issue_number}; processing only this issue")
        print("-" * 60)

    print(f"Found {len(matched_issues)} issue(s) labelled '{target_label}'")
    print("-" * 60)

    if not matched_issues:
        print("No eligible issues found.")
        return

    sessions = load_sessions()

    for issue in matched_issues:
        sessions = process_issue(
            issue=issue,
            owner=owner,
            repo=repo,
            sessions=sessions,
            dry_run=dry_run,
            github_token=github_token,
            devin_org_id=devin_org_id,
            devin_api_key=devin_api_key,
            trigger="CLI",
        )

    if not dry_run:
        sessions = refresh_live_sessions(
            sessions=sessions,
            devin_org_id=devin_org_id,
            devin_api_key=devin_api_key,
        )

        sessions = finalize_sessions_with_prs(
            sessions=sessions,
            owner=owner,
            repo=repo,
            github_token=github_token,
        )

    save_state_and_report(sessions)


if __name__ == "__main__":
    main()
