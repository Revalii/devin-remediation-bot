from textwrap import dedent

from src.devin_client import (
    create_devin_session_dry_run,
    create_devin_session,
    get_devin_session,
)
from src.github_client import (
    create_issue_comment,
    add_issue_label,
    remove_issue_label,
)
from src.session_store import save_sessions
from src.reporter import generate_report, save_report


def build_devin_prompt(issue: dict, owner: str, repo: str) -> str:
    """
    Build a structured prompt that will be sent to Devin.
    """
    issue_number = issue["number"]
    issue_title = issue["title"]
    issue_body = issue.get("body") or ""
    issue_url = issue["html_url"]

    prompt = f"""
You are working on my fork of Apache Superset.

Repository:
https://github.com/{owner}/{repo}

Task:
Resolve GitHub Issue #{issue_number}: {issue_title}

Issue URL:
{issue_url}

Issue body:
{issue_body}

Requirements:
1. Create a new branch named devin/issue-{issue_number}
2. Make the smallest possible change needed to resolve the issue
3. Do not modify unrelated files
4. Avoid broad refactoring
5. Run the relevant test or lint command if practical
6. Open a pull request back to the repository
7. Do not merge the pull request

Pull request description should include:
- Summary of changes
- Files changed
- Tests or checks run
- Any limitations or risks

Important:
This is a low-risk maintenance task. If the task appears larger than expected, stop and explain what human review is needed.
""".strip()

    return prompt


def build_issue_comment(session: dict, dry_run: bool, trigger: str = "CLI") -> str:
    """
    Build the GitHub issue comment body for dry-run or live Devin sessions.
    """
    if dry_run:
        return dedent(f"""
        ### Devin remediation dry-run started

        This issue was picked up by the Devin remediation bot.

        **Trigger:** {trigger}  
        **Mode:** DRY_RUN  
        **Status:** simulated  
        **Session ID:** `{session["session_id"]}`

        No code was changed and no real Devin session was created because `DRY_RUN=true`.

        In live mode, this bot would create a Devin session, track progress, and update this issue with the result.
        """).strip()

    devin_url = session.get("devin_url") or "N/A"

    return dedent(f"""
    ### Devin remediation session started

    This issue was picked up by the Devin remediation bot.

    **Trigger:** {trigger}  
    **Mode:** LIVE  
    **Status:** {session.get("status", "unknown")}  
    **Session ID:** `{session["session_id"]}`  
    **Devin URL:** {devin_url}

    Devin has been asked to make the smallest possible change, avoid unrelated files, open a pull request, and not merge it automatically.

    Human review is still required before any code is merged.
    """).strip()


def process_issue(
        issue: dict,
        owner: str,
        repo: str,
        sessions: dict,
        dry_run: bool,
        github_token: str | None,
        devin_org_id: str,
        devin_api_key: str,
        trigger: str = "CLI",
) -> dict:
    """
    Process one eligible GitHub issue.

    This function is shared by both:
    - CLI scan mode
    - GitHub webhook mode
    """
    issue_number = str(issue["number"])

    print(f"Processing issue #{issue_number}: {issue['title']}")
    print(f"URL: {issue['html_url']}")

    if issue_number in sessions:
        print(f"Existing session found: {sessions[issue_number]['session_id']}")
        print()
        return sessions

    prompt = build_devin_prompt(issue, owner, repo)

    if dry_run:
        session = create_devin_session_dry_run(issue, prompt)

        print("DRY RUN: would create Devin session")
        print(f"Simulated session ID: {session['session_id']}")
    else:
        session = create_devin_session(
            org_id=devin_org_id,
            api_key=devin_api_key,
            issue=issue,
            prompt=prompt,
        )

        print("Real Devin session created")
        print(f"Session ID: {session['session_id']}")
        print(f"Status: {session.get('status', 'unknown')}")
        print(f"Devin URL: {session.get('devin_url')}")

    sessions[issue_number] = session

    if github_token:
        comment_body = build_issue_comment(
            session=session,
            dry_run=dry_run,
            trigger=trigger,
        )

        create_issue_comment(
            owner=owner,
            repo=repo,
            issue_number=issue["number"],
            body=comment_body,
            github_token=github_token,
        )

        print("GitHub issue comment created")

        add_issue_label(
            owner=owner,
            repo=repo,
            issue_number=issue["number"],
            label="devin-in-progress",
            github_token=github_token,
        )

        print("GitHub issue label added: devin-in-progress")
    else:
        print("GITHUB_TOKEN not set; skipping GitHub issue comment and label update")

    print()

    return sessions


def refresh_live_sessions(
        sessions: dict,
        devin_org_id: str,
        devin_api_key: str,
) -> dict:
    """
    Refresh live Devin sessions already stored in sessions.json.
    Dry-run sessions are skipped.
    """
    for issue_number, session in sessions.items():
        session_id = session.get("session_id")

        if not session_id:
            continue

        if str(session_id).startswith("dry-run"):
            continue

        print(f"Refreshing Devin session for issue #{issue_number}: {session_id}")

        try:
            latest = get_devin_session(
                org_id=devin_org_id,
                api_key=devin_api_key,
                session_id=session_id,
            )
        except Exception as error:
            session["last_refresh_error"] = str(error)
            print(f"Failed to refresh session {session_id}: {error}")
            continue

        session["raw_status"] = latest
        session["status"] = latest.get("status", session.get("status", "unknown"))
        session["devin_url"] = latest.get("url", session.get("devin_url"))

        if latest.get("pull_requests"):
            session["pull_requests"] = latest.get("pull_requests")

        if latest.get("pull_request_url"):
            session["pull_request_url"] = latest.get("pull_request_url")

        if latest.get("prs"):
            session["pull_requests"] = latest.get("prs")

    return sessions


def finalize_sessions_with_prs(
        sessions: dict,
        owner: str,
        repo: str,
        github_token: str | None,
) -> dict:
    """
    If a session has produced a PR, update the GitHub issue labels.

    Final state:
    - devin-done
    - needs-human-review
    - remove devin-in-progress
    """
    if not github_token:
        print("GITHUB_TOKEN not set; skipping final label updates")
        return sessions

    for issue_number, session in sessions.items():
        pull_requests = session.get("pull_requests", [])

        if not pull_requests:
            continue

        add_issue_label(
            owner=owner,
            repo=repo,
            issue_number=int(issue_number),
            label="devin-done",
            github_token=github_token,
        )

        add_issue_label(
            owner=owner,
            repo=repo,
            issue_number=int(issue_number),
            label="needs-human-review",
            github_token=github_token,
        )

        remove_issue_label(
            owner=owner,
            repo=repo,
            issue_number=int(issue_number),
            label="devin-in-progress",
            github_token=github_token,
        )

        print(f"Issue #{issue_number} labelled: devin-done, needs-human-review")
        print(f"Issue #{issue_number} label removed: devin-in-progress")

    return sessions


def save_state_and_report(sessions: dict) -> None:
    """
    Save sessions.json and regenerate the Markdown report.
    """
    save_sessions(sessions)

    print("Session state saved to data/sessions.json")

    report = generate_report(sessions)
    save_report(report)

    print("Remediation report saved to reports/remediation_report.md")
