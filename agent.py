"""LLM tool-using agent that solves a data-analysis question.

Uses an OpenAI-compatible Chat Completions endpoint (AIPipe by default) with a
single `run_python` tool. Produces the final JSON object the message asks for,
using the literal token LOG_URL_PLACEHOLDER where the public log URL should go
(substituted by the caller once the log has been uploaded).

Every step is recorded as a JSONL-friendly list of dicts for the run log.
"""
import json
import time
import requests

import config
from tools import RunWorkspace, TOOLS_SPEC

LOG_URL_PLACEHOLDER = "LOG_URL_PLACEHOLDER"

SYSTEM_PROMPT = f"""You are a rigorous data-analyst agent that answers questions delivered over Telegram.

You will receive one or more user messages (the conversation so far). Some tasks are multi-turn;
if so, ANSWER THE LAST QUESTION, using earlier messages only as context.

The final user message tells you the EXACT JSON object to reply with (its keys and the shape of the
answer). Follow it precisely.

How to work:
- Do NOT guess numbers. Use the `run_python` tool to fetch and analyse the actual data. Questions may
  embed data inline, or point at a public dataset URL (MOSPI and similar). Download it, inspect its
  structure, clean it, and compute the answer.
- The Python working directory PERSISTS across tool calls (files you save stay), but in-memory
  variables do NOT. Save intermediate results to disk and reload them when needed. Always print() what
  you need to see.
- Be careful with real-world data: headers on odd rows, footnotes, merged cells, thousands separators,
  units, and "NA"/"-" placeholders. Verify your answer before finalising.

Finishing:
- When you are confident, reply with ONLY the final JSON object exactly as the last message requests.
  No prose, no markdown, no code fence.
- For the value of the "log_url" field, output the literal string "{LOG_URL_PLACEHOLDER}". It will be
  replaced with a real public URL automatically. Do not invent a URL.
- The "answer" field must be shaped EXACTLY as the message specifies (e.g. {{"state": "Assam"}}).
"""


class LLMError(Exception):
    pass


def _chat(messages, tools=None):
    url = f"{config.LLM_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": config.LLM_MODEL, "messages": messages, "temperature": 0}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json()["choices"][0]["message"]


def solve(user_messages, log):
    """Run the agent.

    user_messages: list of plain-text strings (the grader's messages, in order).
    log: list to append JSONL records to.

    Returns the final assistant text (a JSON object string containing
    LOG_URL_PLACEHOLDER where the log url should go).
    """
    ws = RunWorkspace()
    log.append({"ts": time.time(), "type": "run_start", "workspace": ws.path,
                "model": config.LLM_MODEL, "num_messages": len(user_messages)})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for i, m in enumerate(user_messages):
        messages.append({"role": "user", "content": m})
        log.append({"ts": time.time(), "type": "incoming_message", "index": i, "text": m})

    for step in range(config.MAX_AGENT_STEPS):
        msg = _chat(messages, tools=TOOLS_SPEC)
        tool_calls = msg.get("tool_calls") or []

        if tool_calls:
            # Record the assistant's tool-calling turn.
            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })
            log.append({"ts": time.time(), "type": "assistant_tool_calls", "step": step,
                        "content": msg.get("content") or "",
                        "calls": [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                                  for c in tool_calls]})
            for call in tool_calls:
                fn = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                if fn == "run_python":
                    result = ws.run_python(args.get("code", ""))
                else:
                    result = {"ok": False, "stderr": f"unknown tool {fn}"}
                log.append({"ts": time.time(), "type": "tool_result", "step": step,
                            "tool": fn, "code": args.get("code", ""), "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result)[:12000],
                })
            continue

        # No tool calls -> this is the final answer.
        content = (msg.get("content") or "").strip()
        log.append({"ts": time.time(), "type": "assistant_final", "step": step, "content": content})
        return content

    log.append({"ts": time.time(), "type": "error", "message": "max steps reached"})
    # Best-effort: ask for a final answer with no tools.
    messages.append({"role": "user",
                     "content": "You are out of steps. Reply now with ONLY the final JSON object as instructed."})
    final = _chat(messages)
    content = (final.get("content") or "").strip()
    log.append({"ts": time.time(), "type": "assistant_final_forced", "content": content})
    return content
