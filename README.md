# Devin Remediation Bot

An event-driven automation that uses the Devin API to remediate low-risk maintenance issues in an Apache Superset fork.

This project was built for the Cognition take-home challenge. It demonstrates how Devin can be used as a core automation primitive in an engineering workflow: detecting eligible GitHub issues, creating Devin sessions programmatically, tracking remediation progress, producing pull requests, and reporting status for engineering leaders.

## Overview

The target repository is a fork of Apache Superset:

```text
https://github.com/Revalii/superset
```

The automation repository is:

```text
https://github.com/Revalii/devin-remediation-bot
```

The selected use case is:

> Automatically remediate low-risk maintenance issues in a large open-source codebase.

Examples of eligible tasks include:

* Documentation wording improvements
* Small code comment cleanup
* Minor code quality improvements
* Lightweight test coverage additions

The bot does not merge code automatically. Devin is instructed to create a pull request only. Human review remains required before any change is merged.

---

## What the Bot Does

The bot can be triggered by GitHub issue activity through a webhook.

When an issue receives the `devin-remediate` label, the bot checks whether the issue also has one of the allowed low-risk task labels:

```text
docs
code-quality
comment-cleanup
test
```

If the issue passes the checks, the bot:

1. Builds a structured Devin prompt from the GitHub issue.
2. Creates a Devin session using the Devin API.
3. Saves the issue-to-session mapping in `data/sessions.json`.
4. Adds a GitHub comment with the Devin session details.
5. Adds the `devin-in-progress` label.
6. Generates or updates `reports/remediation_report.md`.

When Devin opens a pull request from a branch named `devin/issue-{number}`, the bot handles the GitHub `pull_request.opened` webhook event and:

1. Extracts the issue number from the branch name.
2. Adds the PR URL to the stored session record.
3. Adds the `devin-done` and `needs-human-review` labels.
4. Removes the `devin-in-progress` label.
5. Regenerates the Markdown report.

---

## Architecture

```text
GitHub issue labelled devin-remediate
        |
        v
GitHub webhook: issues.labeled
        |
        v
webhook_server.py
        |
        v
remediation.py
        |
        v
Devin API session created
        |
        v
GitHub issue comment + devin-in-progress label
        |
        v
Devin opens pull request
        |
        v
GitHub webhook: pull_request.opened
        |
        v
Update sessions.json, report, and final issue labels
```

---

## Project Structure

```text
devin-remediation-bot/
├── README.md
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
├── data/
│   └── sessions.json
├── reports/
│   └── remediation_report.md
└── src/
    ├── __init__.py
    ├── main.py
    ├── webhook_server.py
    ├── remediation.py
    ├── github_client.py
    ├── devin_client.py
    ├── session_store.py
    └── reporter.py
```

### Key Files

| File                    | Purpose                                    |
| ----------------------- | ------------------------------------------ |
| `src/main.py`           | CLI scan mode for manual runs or refreshes |
| `src/webhook_server.py` | Flask webhook server for GitHub events     |
| `src/remediation.py`    | Shared remediation logic                   |
| `src/devin_client.py`   | Devin API client                           |
| `src/github_client.py`  | GitHub issue comment and label API client  |
| `src/session_store.py`  | Reads and writes `data/sessions.json`      |
| `src/reporter.py`       | Generates `reports/remediation_report.md`  |

---

## Trigger Model

The project supports two entry points.

### 1. Webhook Mode

This is the primary event-driven mode.

The bot listens for:

```text
issues.labeled
pull_request.opened
```

The intended label flow is:

```text
docs / code-quality / comment-cleanup / test = task classification
devin-remediate = execution trigger
```

Recommended usage:

1. Create a GitHub issue.
2. Add a low-risk task label, such as `docs`.
3. Add `devin-remediate` last.

This prevents accidental execution and avoids duplicate session creation when multiple labels are added.

### 2. CLI Mode

The CLI mode scans open issues in the target repo:

```bash
python -m src.main
```

This mode is useful for local testing, manual refreshes, or future scheduled execution.

---

## Environment Variables

Create a local `.env` file based on `.env.example`.

```env
GITHUB_OWNER=Revalii
GITHUB_REPO=superset
TARGET_LABEL=devin-remediate
ALLOWED_TASK_LABELS=docs,code-quality,comment-cleanup,test
TARGET_ISSUE_NUMBER=
DRY_RUN=true

GITHUB_TOKEN=
DEVIN_ORG_ID=
DEVIN_API_KEY=
GITHUB_WEBHOOK_SECRET=
```

### Variable Details

| Variable                | Description                                       |
| ----------------------- | ------------------------------------------------- |
| `GITHUB_OWNER`          | Owner of the target repository                    |
| `GITHUB_REPO`           | Target repository name                            |
| `TARGET_LABEL`          | Label that triggers remediation                   |
| `ALLOWED_TASK_LABELS`   | Comma-separated allowlist of low-risk task labels |
| `TARGET_ISSUE_NUMBER`   | Optional safety guard to process only one issue   |
| `DRY_RUN`               | If `true`, simulates Devin session creation       |
| `GITHUB_TOKEN`          | GitHub token with issue/comment/label permissions |
| `DEVIN_ORG_ID`          | Devin organization ID                             |
| `DEVIN_API_KEY`         | Devin API key                                     |
| `GITHUB_WEBHOOK_SECRET` | Secret used to verify GitHub webhook signatures   |

Do not commit `.env` to GitHub.

---

## Local Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Run CLI mode:

```bash
python -m src.main
```

Run webhook mode:

```bash
python -m src.webhook_server
```

By default, the webhook server runs on:

```text
http://localhost:8000/webhook
```

To expose it to GitHub during local testing, use ngrok:

```bash
ngrok http 8000
```

Then configure the GitHub webhook payload URL as:

```text
https://your-ngrok-url.ngrok-free.dev/webhook
```

The GitHub webhook should subscribe to:

```text
Issues
Pull requests
```

---

## Docker Usage

Build the image:

```bash
docker build -t devin-remediation-bot .
```

Run CLI mode:

```bash
docker run --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/reports:/app/reports" \
  devin-remediation-bot
```

Run webhook mode:

```bash
docker run --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/reports:/app/reports" \
  devin-remediation-bot \
  python -m src.webhook_server
```

Then run ngrok:

```bash
ngrok http 8000
```

---

## Dry Run Mode

Dry run mode is used to validate the workflow without creating a real Devin session.

Set:

```env
DRY_RUN=true
```

In dry run mode, the bot:

* Detects eligible issues
* Creates simulated session records
* Comments on GitHub issues
* Adds `devin-in-progress`
* Generates `sessions.json`
* Generates `remediation_report.md`

It does not call the real Devin API.

---

## Live Mode

Live mode creates real Devin sessions.

Set:

```env
DRY_RUN=false
```

In live mode, the bot:

* Calls the Devin API
* Creates a real Devin session
* Links the Devin session back to the GitHub issue
* Tracks PR output through the `pull_request.opened` webhook
* Updates labels and reports when a PR is created

---

## Observability

The project provides several observable outputs for technical users and engineering leaders.

### GitHub Issue Labels

| Label                | Meaning                                      |
| -------------------- | -------------------------------------------- |
| `devin-remediate`    | Human approval to let Devin handle the issue |
| `devin-in-progress`  | Devin session has started                    |
| `devin-done`         | Devin produced a remediation output          |
| `needs-human-review` | A human engineer should review the PR        |

### GitHub Issue Comments

The bot writes comments containing:

* Trigger source
* Mode: dry-run or live
* Session ID
* Devin session URL
* Human review note

### Session Store

The bot saves issue-to-session mappings in:

```text
data/sessions.json
```

This includes:

* Issue number
* Issue title
* GitHub issue URL
* Devin session ID
* Devin session URL
* Status
* Pull request URL, when available

### Markdown Report

The bot generates:

```text
reports/remediation_report.md
```

The report includes:

* Total sessions tracked
* Simulated sessions
* Running sessions
* Completed sessions
* Failed sessions
* Issue details
* Session IDs
* PR links
* Human review boundary

This answers the question:

> If I were an engineering leader, how would I know this is working?

---

## Demo Result

During testing, the bot successfully processed a live Superset documentation issue.

The bot:

1. Detected a labelled GitHub issue.
2. Created a real Devin session.
3. Devin created a branch named `devin/issue-1`.
4. Devin opened a pull request.
5. The bot updated GitHub issue labels and generated a remediation report.

Example output:

```text
Issue #1
Devin session created
Pull request opened
Status updated to needs-human-review
```

The pull request remained unmerged to preserve the human review boundary.

---

## Safety Controls

The bot includes several safety controls:

1. Devin only runs when the `devin-remediate` label is added.
2. The issue must also have an allowed low-risk task label.
3. `TARGET_ISSUE_NUMBER` can restrict live testing to a single issue.
4. Existing sessions are stored in `sessions.json` to avoid duplicate processing.
5. Devin is instructed not to merge pull requests.
6. Human review remains required before merge.

---

## Known Limitations

This is a take-home MVP, not a production deployment.

Current limitations include:

* Local webhook testing depends on ngrok.
* State is stored locally in `data/sessions.json`.
* The PR-to-issue link depends on Devin using the branch format `devin/issue-{number}`.
* The bot does not perform deep semantic risk classification of issue content.
* Production deployment would benefit from persistent storage, stronger deduplication, hosted webhook infrastructure, and more robust retry handling.

---

## Future Improvements

Potential extensions include:

* Deploying the webhook service to a cloud runtime
* Replacing local JSON state with a database
* Adding scheduled polling as a fallback
* Adding richer metrics and dashboards
* Supporting Jira or Linear tickets
* Integrating security scan results
* Adding stricter approval workflows
* Adding GitHub Actions support for scheduled refreshes

---

## Summary

This project demonstrates an event-driven Devin automation for engineering maintenance work.

It uses GitHub labels and webhooks to trigger remediation, Devin API sessions to perform the work, GitHub pull requests as reviewable outputs, and lightweight reporting to provide visibility for engineering leaders.

The automation is intentionally scoped to low-risk tasks and keeps humans in control of final code review and merge decisions.
