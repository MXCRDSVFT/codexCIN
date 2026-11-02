#!/usr/bin/env python3
"""Authoritative codexCIN adapter for the official GitHub @codex PR actor.

No network request is made unless --post is supplied. Authentication is handled
by the locally configured GitHub CLI; credentials are never persisted here.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone


def build_review_request(repository: str, pr_number: int, instructions: str = "") -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must use owner/name format")
    if type(pr_number) is not int or pr_number <= 0:
        raise ValueError("pr_number must be a positive integer")
    if not isinstance(instructions, str):
        raise TypeError("instructions must be a string")
    instructions = instructions.strip()
    if len(instructions) > 20000:
        raise ValueError("instructions exceed the supported review-request length")
    comment = "@codex review"
    if instructions:
        comment += "\n\n" + instructions
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "authority": "MXCRDSVFT/codexCIN",
        "agent": "@codex",
        "profile_url": "https://github.com/codex",
        "upstream_repo": "https://github.com/openai/codex",
        "repository": repository,
        "pr_number": pr_number,
        "comment": comment,
        "pull_request_url": f"https://github.com/{repository}/pull/{pr_number}",
    }


def dispatch_review(request: dict, *, post: bool = False, timeout_seconds: float = 30.0) -> dict:
    if not post:
        return {**request, "sent": False, "status": "explicit_authorization_required"}
    gh = shutil.which("gh")
    if not gh:
        return {**request, "sent": False, "status": "github_cli_unavailable"}
    try:
        proc = subprocess.run(
            [
                gh,
                "api",
                "--method",
                "POST",
                f"repos/{request['repository']}/issues/{request['pr_number']}/comments",
                "-f",
                f"body={request['comment']}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1.0, float(timeout_seconds)),
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {
            **request, "sent": False, "status": "dispatch_error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    if proc.returncode != 0:
        return {
            **request, "sent": False, "status": "github_api_error",
            "returncode": proc.returncode,
        }
    try:
        payload = json.loads(proc.stdout)
        comment_url = payload.get("html_url") if isinstance(payload, dict) else None
    except (ValueError, TypeError):
        comment_url = None
    if not comment_url:
        return {**request, "sent": False, "status": "unverified_api_response"}
    return {**request, "sent": True, "status": "posted", "comment_url": comment_url}


def main() -> int:
    parser = argparse.ArgumentParser(description="codexCIN authoritative GitHub @codex PR adapter")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--instructions", default="")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--post", action="store_true", help="Explicitly send the GitHub comment")
    args = parser.parse_args()
    result = dispatch_review(
        build_review_request(args.repository, args.pr_number, args.instructions),
        post=args.post,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not args.post or result.get("sent") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
