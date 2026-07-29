"""Telegram data-analyst bot (long-polling).

Receives plain-text data-analysis questions from the grader (a real Telegram
user account), solves them with an LLM tool-using agent, publishes the run log,
and replies with exactly one JSON object: {"answer": ..., "log_url": ...}.

Multi-turn handling: messages from a chat are buffered and processed once the
chat has been idle for CHAT_DEBOUNCE_SECONDS, so a burst of messages is answered
once, against the LAST question.

Run with:  python bot.py
"""
import json
import time
import traceback
import requests

import config
import agent
import log_store

API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


# ---------- Telegram helpers ----------

def get_updates(offset):
    r = requests.get(f"{API}/getUpdates",
                     params={"offset": offset, "timeout": 3},
                     timeout=15)
    r.raise_for_status()
    return r.json().get("result", [])


def send_message(chat_id, text):
    # No parse_mode: we send raw JSON text exactly.
    r = requests.post(f"{API}/sendMessage",
                      json={"chat_id": chat_id, "text": text},
                      timeout=30)
    if r.status_code != 200:
        print(f"[send] HTTP {r.status_code}: {r.text[:200]}")


# ---------- Final-answer assembly ----------

def extract_json_object(text):
    """Pull the first balanced {...} JSON object out of the model's text."""
    text = text.strip()
    if text.startswith("```"):
        # strip code fences
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
    return None


def _replace_placeholder(obj, url):
    if isinstance(obj, dict):
        return {k: _replace_placeholder(v, url) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_placeholder(v, url) for v in obj]
    if isinstance(obj, str) and obj == agent.LOG_URL_PLACEHOLDER:
        return url
    return obj


def build_reply(final_text, log_url):
    """Turn the agent's final text into the exact JSON string to send."""
    obj = extract_json_object(final_text)
    if obj is None:
        # Last resort: wrap whatever we got so the reply is still valid JSON.
        obj = {"answer": final_text, "log_url": log_url}
    obj = _replace_placeholder(obj, log_url)
    if isinstance(obj, dict):
        # Enforce the contract: log_url must be present and real.
        obj["log_url"] = log_url
    return json.dumps(obj, ensure_ascii=False)


# ---------- Orchestration ----------

def process_chat(chat_id, messages):
    print(f"[process] chat {chat_id}: {len(messages)} message(s)")
    log = []
    try:
        final_text = agent.solve(messages, log)
    except Exception as e:
        log.append({"ts": time.time(), "type": "fatal_error",
                    "error": str(e), "trace": traceback.format_exc()})
        final_text = json.dumps({"answer": None, "error": str(e),
                                 "log_url": agent.LOG_URL_PLACEHOLDER})
    log_url = log_store.publish(log)
    reply = build_reply(final_text, log_url)
    print(f"[process] chat {chat_id} reply: {reply[:200]}")
    send_message(chat_id, reply)


def main():
    print(f"Bot starting. Model={config.LLM_MODEL} via {config.LLM_BASE_URL}")
    me = requests.get(f"{API}/getMe", timeout=15).json()
    print("getMe:", me.get("result", me))

    offset = 0
    buffers = {}  # chat_id -> {"msgs": [...], "last": ts}

    while True:
        try:
            updates = get_updates(offset)
        except Exception as e:
            print(f"[poll] error: {e}")
            time.sleep(3)
            continue

        for u in updates:
            offset = max(offset, u["update_id"] + 1)
            msg = u.get("message") or u.get("edited_message")
            if not msg:
                continue
            text = msg.get("text")
            chat_id = msg["chat"]["id"]
            if not text:
                continue
            if text.strip().startswith("/"):
                # ignore bot commands like /start
                continue
            buf = buffers.setdefault(chat_id, {"msgs": [], "last": 0})
            buf["msgs"].append(text)
            buf["last"] = time.time()
            print(f"[recv] chat {chat_id}: {text[:120]}")

        # Process chats that have gone quiet.
        now = time.time()
        for chat_id in list(buffers.keys()):
            buf = buffers[chat_id]
            if buf["msgs"] and (now - buf["last"]) >= config.CHAT_DEBOUNCE_SECONDS:
                msgs = buf["msgs"]
                buffers.pop(chat_id, None)
                try:
                    process_chat(chat_id, msgs)
                except Exception as e:
                    print(f"[process] fatal for chat {chat_id}: {e}")
                    traceback.print_exc()


if __name__ == "__main__":
    main()
