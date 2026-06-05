import hashlib
import hmac
import os

from flask import Flask, jsonify, request
from dotenv import load_dotenv

from src.session_store import load_sessions
from src.remediation import (
    process_issue,
    finalize_sessions_with_prs,
    save_state_and_report,
)

app = Flask(__name__)


def verify_github_signature(
    payload_body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """
    Verify GitHub webhook signature using X-Hub-Signature-256.
    """
    if not signature_header:
        return False

    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature_header)


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

    If ALLOWED_TASK_LABELS is empty, allow all task types.
    """
    if not allowed_labels:
        return True

    issue_labels = get_issue_label_names(issue)
    return bool(issue_labels.intersection(allowed_labels))


def extract_issue_number_from_branch(branch_name: str) -> str | None:
    """
    Extract issue number from a Devin branch name.

    Expected branch format:
    devin/issue-6
    """
    prefix = "devin/issue-"

    if not branch_name.startswith(prefix):
        return None

    issue_number = branch_name.replace(prefix, "", 1)

    if not issue_number.isdigit():
        return None

    return issue_number


def handle_pull_request_opened(payload: dict, github_token: str | None):
    """
    Handle GitHub pull_request.opened event.

    When Devin opens a PR from branch devin/issue-{number},
    update the matching session record and finalize issue labels.
    """
    pull_request = payload.get("pull_request", {})
    repository = payload.get("repository", {})

    if not pull_request or not repository:
        return jsonify({"error": "Missing pull_request or repository in payload"}), 400

    owner = repository["owner"]["login"]
    repo = repository["name"]

    pr_url = pull_request.get("html_url")
    pr_state = pull_request.get("state", "open")
    branch_name = pull_request.get("head", {}).get("ref", "")

    print(f"Received PR opened event from branch: {branch_name}")

    issue_number = extract_issue_number_from_branch(branch_name)

    if not issue_number:
        return jsonify({
            "ignored": True,
            "reason": f"PR branch '{branch_name}' does not match devin/issue-* pattern",
        }), 200

    sessions = load_sessions()

    if issue_number not in sessions:
        return jsonify({
            "ignored": True,
            "reason": f"No session record found for issue #{issue_number}",
        }), 200

    sessions[issue_number]["pull_requests"] = [
        {
            "pr_url": pr_url,
            "pr_state": pr_state,
        }
    ]

    sessions[issue_number]["status"] = "waiting_for_human_review"
    sessions[issue_number]["status_detail"] = "pr_opened_waiting_for_human_review"

    sessions = finalize_sessions_with_prs(
        sessions=sessions,
        owner=owner,
        repo=repo,
        github_token=github_token,
    )

    save_state_and_report(sessions)

    return jsonify({
        "processed": True,
        "trigger": "pull_request_opened",
        "issue_number": issue_number,
        "pr_url": pr_url,
        "status": sessions[issue_number].get("status"),
    }), 200


def handle_issue_labeled(
    payload: dict,
    github_token: str | None,
    target_label: str,
    target_issue_number: str | None,
    allowed_task_labels: set[str],
    dry_run: bool,
    devin_org_id: str,
    devin_api_key: str,
):
    """
    Handle GitHub issues.labeled event.

    Execution rule:
    - The newly added label must be the target execution label, e.g. devin-remediate.
    - The issue must already have at least one allowed task label, e.g. docs.
    """
    action = payload.get("action")
    label = payload.get("label", {})
    label_name = label.get("name")

    print(f"Received GitHub event: issues, action: {action}, label: {label_name}")

    if action != "labeled":
        return jsonify({
            "ignored": True,
            "reason": f"Unsupported issue action: {action}",
        }), 200

    # Important: only the target label acts as the execution trigger.
    # Other labels, such as docs/code-quality/test, are classification labels only.
    if label_name != target_label:
        return jsonify({
            "ignored": True,
            "reason": f"Label '{label_name}' is not the trigger label '{target_label}'",
        }), 200

    issue = payload.get("issue")
    repository = payload.get("repository", {})

    if not issue or not repository:
        return jsonify({"error": "Missing issue or repository in payload"}), 400

    issue_labels = get_issue_label_names(issue)

    if target_label not in issue_labels:
        return jsonify({
            "ignored": True,
            "reason": f"Issue does not have target label '{target_label}'",
        }), 200

    if not has_allowed_task_label(issue, allowed_task_labels):
        return jsonify({
            "ignored": True,
            "reason": (
                "Issue is missing an allowed task label. "
                f"Required one of: {sorted(allowed_task_labels)}"
            ),
        }), 200

    owner = repository["owner"]["login"]
    repo = repository["name"]

    issue_number = str(issue["number"])

    print(f"Webhook issue number: {issue_number}")
    print(f"TARGET_ISSUE_NUMBER: {target_issue_number}")
    print(f"Issue labels: {sorted(issue_labels)}")
    print(f"Allowed task labels: {sorted(allowed_task_labels)}")

    if target_issue_number and issue_number != target_issue_number:
        print(f"Ignored issue #{issue_number}: target issue is #{target_issue_number}")

        return jsonify({
            "ignored": True,
            "reason": f"TARGET_ISSUE_NUMBER={target_issue_number}; issue #{issue_number} skipped",
        }), 200

    sessions = load_sessions()

    if issue_number in sessions:
        print(f"Ignored issue #{issue_number}: existing session found")

        return jsonify({
            "ignored": True,
            "reason": f"Issue #{issue_number} already has session {sessions[issue_number]['session_id']}",
        }), 200

    sessions = process_issue(
        issue=issue,
        owner=owner,
        repo=repo,
        sessions=sessions,
        dry_run=dry_run,
        github_token=github_token,
        devin_org_id=devin_org_id,
        devin_api_key=devin_api_key,
        trigger="GitHub webhook",
    )

    save_state_and_report(sessions)

    return jsonify({
        "processed": True,
        "trigger": "issues_labeled",
        "dry_run": dry_run,
        "issue_number": issue_number,
        "session_id": sessions[issue_number]["session_id"],
        "status": sessions[issue_number].get("status"),
    }), 200


@app.route("/webhook", methods=["POST"])
def github_webhook():
    load_dotenv()

    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    github_token = os.getenv("GITHUB_TOKEN") or None

    target_label = os.getenv("TARGET_LABEL", "devin-remediate")
    target_issue_number = os.getenv("TARGET_ISSUE_NUMBER") or None

    allowed_task_labels = parse_allowed_task_labels(
        os.getenv("ALLOWED_TASK_LABELS", "")
    )

    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    devin_org_id = os.getenv("DEVIN_ORG_ID") or ""
    devin_api_key = os.getenv("DEVIN_API_KEY") or ""

    if not webhook_secret:
        return jsonify({"error": "GITHUB_WEBHOOK_SECRET is not set"}), 500

    signature_header = request.headers.get("X-Hub-Signature-256")

    if not verify_github_signature(request.data, signature_header, webhook_secret):
        return jsonify({"error": "Invalid GitHub webhook signature"}), 401

    event_name = request.headers.get("X-GitHub-Event")
    payload = request.get_json() or {}

    if event_name == "pull_request":
        action = payload.get("action")

        print(f"Received GitHub event: {event_name}, action: {action}")

        if action != "opened":
            return jsonify({
                "ignored": True,
                "reason": f"Unsupported pull_request action: {action}",
            }), 200

        return handle_pull_request_opened(
            payload=payload,
            github_token=github_token,
        )

    if event_name == "issues":
        return handle_issue_labeled(
            payload=payload,
            github_token=github_token,
            target_label=target_label,
            target_issue_number=target_issue_number,
            allowed_task_labels=allowed_task_labels,
            dry_run=dry_run,
            devin_org_id=devin_org_id,
            devin_api_key=devin_api_key,
        )

    return jsonify({
        "ignored": True,
        "reason": f"Unsupported event: {event_name}",
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)