"""Publish a run log as a public, wget-able JSONL file.

Primary sink: commit the JSONL to the public GitHub repo via the Contents API and
return its raw.githubusercontent.com URL. This needs GITHUB_TOKEN + GITHUB_REPO.

If GitHub is not configured, the log is written locally and a file path is returned
(useful for local testing; not publicly reachable).
"""
import base64
import json
import os
import time
import uuid
import requests

import config


def _jsonl(records) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records) + "\n"


def _run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]


def publish(records) -> str:
    """Upload the log records as JSONL. Returns a public URL (or local path fallback)."""
    body = _jsonl(records)
    run_id = _run_id()
    path = f"{config.LOG_DIR_IN_REPO}/run-{run_id}.jsonl"

    if config.GITHUB_TOKEN and config.GITHUB_REPO:
        try:
            return _github_put(path, body)
        except Exception as e:  # fall through to local
            print(f"[log_store] GitHub upload failed: {e}")

    # Local fallback
    os.makedirs(config.LOG_DIR_IN_REPO, exist_ok=True)
    local = os.path.join(config.LOG_DIR_IN_REPO, f"run-{run_id}.jsonl")
    with open(local, "w", encoding="utf-8") as f:
        f.write(body)
    return "file://" + os.path.abspath(local)


def _github_put(path: str, body: str) -> str:
    url = f"https://api.github.com/repos/{config.GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "message": f"agent run log {path}",
        "content": base64.b64encode(body.encode("utf-8")).decode("ascii"),
        "branch": config.GITHUB_BRANCH,
    }
    resp = requests.put(url, headers=headers, json=payload, timeout=60)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"GitHub PUT {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    download_url = data.get("content", {}).get("download_url")
    if download_url:
        return download_url
    return f"https://raw.githubusercontent.com/{config.GITHUB_REPO}/{config.GITHUB_BRANCH}/{path}"
