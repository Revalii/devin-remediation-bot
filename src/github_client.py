import requests


def create_issue_comment(
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
    github_token: str,
) -> dict:
    """
    Create a comment on a GitHub issue.
    """
    if not github_token:
        raise ValueError("GITHUB_TOKEN is required to create issue comments.")

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
    }

    payload = {
        "body": body,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20)

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to create issue comment: {response.status_code} {response.text}"
        )

    return response.json()

def add_issue_label(
    owner: str,
    repo: str,
    issue_number: int,
    label: str,
    github_token: str,
) -> dict:
    """
    Add a label to a GitHub issue.
    """
    if not github_token:
        raise ValueError("GITHUB_TOKEN is required to add issue labels.")

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/labels"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
    }

    payload = {
        "labels": [label],
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20)

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to add issue label: {response.status_code} {response.text}"
        )

    return response.json()

def remove_issue_label(
    owner: str,
    repo: str,
    issue_number: int,
    label: str,
    github_token: str,
) -> None:
    """
    Remove a label from a GitHub issue.
    """
    if not github_token:
        raise ValueError("GITHUB_TOKEN is required to remove issue labels.")

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/labels/{label}"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
    }

    response = requests.delete(url, headers=headers, timeout=20)

    if response.status_code not in (200, 204, 404):
        raise RuntimeError(
            f"Failed to remove issue label: {response.status_code} {response.text}"
        )