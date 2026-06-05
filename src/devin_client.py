from datetime import datetime, timezone
import requests


def create_devin_session_dry_run(issue: dict, prompt: str) -> dict:
    """
    Simulate Devin session creation without calling the real Devin API.
    """
    issue_number = issue["number"]

    return {
        "session_id": f"dry-run-session-issue-{issue_number}",
        "status": "simulated",
        "issue_number": issue_number,
        "issue_title": issue["title"],
        "issue_url": issue["html_url"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt_preview": prompt[:500],
        "devin_url": None,
        "pull_requests": [],
    }


def create_devin_session(
        org_id: str,
        api_key: str,
        issue: dict,
        prompt: str,
) -> dict:
    """
    Create a real Devin session using the Devin API.
    """
    if not org_id:
        raise ValueError("DEVIN_ORG_ID is required.")

    if not api_key:
        raise ValueError("DEVIN_API_KEY is required.")

    issue_number = issue["number"]

    url = f"https://api.devin.ai/v3/organizations/{org_id}/sessions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "title": f"Remediate Superset issue #{issue_number}: {issue['title']}",
        "prompt": prompt,
        "repos": [f"https://github.com/Revalii/superset"],
        "tags": [
            "take-home",
            "superset",
            "devin-remediation-bot",
            f"issue-{issue_number}",
        ],
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to create Devin session: {response.status_code} {response.text}"
        )

    data = response.json()

    return {
        "session_id": data.get("session_id"),
        "status": data.get("status", "unknown"),
        "issue_number": issue_number,
        "issue_title": issue["title"],
        "issue_url": issue["html_url"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt_preview": prompt[:500],
        "devin_url": data.get("url"),
        "pull_requests": data.get("pull_requests", []),
        "raw_status": data,
    }


def get_devin_session(
        org_id: str,
        api_key: str,
        session_id: str,
) -> dict:
    """
    Fetch the latest state of a Devin session from the Devin API.
    """
    if not org_id:
        raise ValueError("DEVIN_ORG_ID is required.")

    if not api_key:
        raise ValueError("DEVIN_API_KEY is required.")

    if not session_id:
        raise ValueError("session_id is required.")

    url = f"https://api.devin.ai/v3/organizations/{org_id}/sessions/{session_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    response = requests.get(url, headers=headers, timeout=60)

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch Devin session: {response.status_code} {response.text}"
        )

    return response.json()
