#!/usr/bin/env python3
"""Reconcile native GitHub issue dependencies and parent/sub-issue state."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Protocol


DEFAULT_LABELS = {
    "blocked": "blocked",
    "ready_for_agent": "ready-for-agent",
    "in_progress": "in-progress",
    "ready_for_human": "ready-for-human",
}


class IssueAPI(Protocol):
    def issue(self, number: int) -> dict: ...

    def related(self, number: int, relation: str) -> list[dict]: ...

    def blocker_satisfied(self, issue: dict) -> bool: ...

    def update(self, number: int, **changes: object) -> None: ...


class GitHubAPI:
    def __init__(self, repository: str, binary: str = "gh") -> None:
        self.repository = repository
        self.binary = binary
        self._merged: dict[int, bool] = {}

    def _get(self, path: str, paginate: bool = False) -> object:
        command = [
            self.binary,
            "api",
            "--method",
            "GET",
            f"repos/{self.repository}/{path}",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
        ]
        if paginate:
            command += ["--paginate", "--slurp", "-f", "per_page=100"]
        result = subprocess.run(
            command, check=True, capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        if paginate:
            return [item for page in data for item in page]
        return data

    def issue(self, number: int) -> dict:
        return self._get(f"issues/{number}")  # type: ignore[return-value]

    def related(self, number: int, relation: str) -> list[dict]:
        paths = {
            "blocked_by": f"issues/{number}/dependencies/blocked_by",
            "blocking": f"issues/{number}/dependencies/blocking",
            "sub_issues": f"issues/{number}/sub_issues",
        }
        if relation == "parent":
            try:
                return [self._get(f"issues/{number}/parent")]  # type: ignore[list-item]
            except subprocess.CalledProcessError as error:
                if "HTTP 404" in (error.stderr or "") or "Not Found" in (error.stderr or ""):
                    return []
                raise
        return self._get(paths[relation], paginate=True)  # type: ignore[return-value]

    def blocker_satisfied(self, issue: dict) -> bool:
        if issue["state"] != "closed":
            return False
        number = int(issue["number"])
        if number not in self._merged:
            result = subprocess.run(
                [
                    self.binary,
                    "issue",
                    "view",
                    str(number),
                    "--repo",
                    self.repository,
                    "--json",
                    "closedByPullRequestsReferences",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            pull_requests = json.loads(result.stdout)["closedByPullRequestsReferences"]
            self._merged[number] = False
            for pull_request in pull_requests:
                result = subprocess.run(
                    [
                        self.binary,
                        "pr",
                        "view",
                        pull_request["url"],
                        "--json",
                        "state,mergedAt",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                pull_request_state = json.loads(result.stdout)
                if (
                    pull_request_state["state"] == "MERGED"
                    or pull_request_state["mergedAt"] is not None
                ):
                    self._merged[number] = True
                    break
        return self._merged[number]

    def update(self, number: int, **changes: object) -> None:
        subprocess.run(
            [
                self.binary,
                "api",
                "--method",
                "PATCH",
                f"repos/{self.repository}/issues/{number}",
                "-H",
                "X-GitHub-Api-Version: 2022-11-28",
                "--input",
                "-",
            ],
            input=json.dumps(changes),
            check=True,
            text=True,
        )


def label_names(issue: dict) -> set[str]:
    return {
        label if isinstance(label, str) else label["name"]
        for label in issue.get("labels", [])
    }


def reconcile_frontier(
    api: IssueAPI,
    number: int,
    labels: dict[str, str],
    reset_active: bool = False,
) -> None:
    issue = api.issue(number)
    if issue["state"] != "open":
        return

    current = label_names(issue)
    active = {labels["in_progress"], labels["ready_for_human"]}
    released = {labels["blocked"], labels["ready_for_agent"]}
    if not current & set(labels.values()):
        return
    desired = current - released
    blockers = api.related(number, "blocked_by")
    if any(not api.blocker_satisfied(blocker) for blocker in blockers):
        desired -= active
        desired.add(labels["blocked"])
    elif reset_active or not current & active or current & released:
        desired -= active
        desired.add(
            labels["ready_for_agent"]
        )
    if desired != current:
        api.update(number, labels=sorted(desired))


def reconcile_parent(
    api: IssueAPI, number: int, labels: dict[str, str]
) -> bool:
    parent = api.issue(number)
    if not label_names(parent) & set(labels.values()):
        return False
    children = api.related(number, "sub_issues")
    if not children:
        return False

    target = "closed" if all(api.blocker_satisfied(child) for child in children) else "open"
    if parent["state"] == target:
        return False

    changes: dict[str, object] = {"state": target}
    if target == "open":
        current = label_names(parent) - {
            labels["blocked"],
            labels["ready_for_agent"],
            labels["ready_for_human"],
        }
        current.add(labels["in_progress"])
        changes["labels"] = sorted(current)
    api.update(number, **changes)
    return True


def reconcile(
    api: IssueAPI,
    event_number: int,
    labels: dict[str, str],
    event_action: str = "",
) -> None:
    queue = [(event_number, event_action == "reopened")]
    seen: set[int] = set()
    while queue:
        number, reset_active = queue.pop(0)
        if number in seen:
            continue
        seen.add(number)

        reconcile_frontier(api, number, labels, reset_active)
        for dependent in api.related(number, "blocking"):
            reconcile_frontier(api, dependent["number"], labels)
        reconcile_parent(api, number, labels)

        parents = api.related(number, "parent")
        if parents:
            parent_number = parents[0]["number"]
            if reconcile_parent(api, parent_number, labels):
                queue.append((parent_number, False))


def configured_labels(path: Path = Path("docs/agents/harness.json")) -> dict[str, str]:
    if not path.exists():
        return DEFAULT_LABELS.copy()
    config = json.loads(path.read_text())
    return DEFAULT_LABELS | config.get("labels", {})


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    reconcile(
        GitHubAPI(repository),
        int(event["issue"]["number"]),
        configured_labels(),
        event.get("action", ""),
    )


if __name__ == "__main__":
    main()
