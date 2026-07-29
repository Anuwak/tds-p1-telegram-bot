# TDS 2026 P1 — Data-Analyst Telegram Bot

An LLM agent that answers data-analysis questions sent over Telegram and replies
with a single JSON object:

```json
{"answer": <answer in the shape the question asks for>, "log_url": "https://.../run-*.jsonl"}
```

The agent uses a `run_python` tool to fetch and analyse the actual data (MOSPI and
similar public datasets) rather than guessing, and publishes a JSONL log of every
step to a public URL.

## How it works

```
Telegram user (grader) ──▶ bot.py (long-poll getUpdates)
                              │  buffers a burst, answers the last question
                              ▼
                          agent.py  ──run_python tool──▶ subprocess (pandas/requests/bs4)
                              │  produces final JSON (with LOG_URL_PLACEHOLDER)
                              ▼
                          log_store.py ──▶ commits run-<id>.jsonl to this public repo
                              │  returns the raw.githubusercontent.com URL
                              ▼
                          reply: {"answer": ..., "log_url": "<raw url>"}
```

## Setup

```bash
python -m venv .venv && . .venv/Scripts/activate   # optional
pip install -r requirements.txt
cp .env.example .env      # then edit .env
python bot.py
```

Fill `.env`:

| var | what |
|-----|------|
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | AIPipe (https://aipipe.org) by default |
| `GITHUB_TOKEN` / `GITHUB_REPO` | a PAT with contents:write; the (public) repo to store logs in |

Keep the process running during grading. Because it uses long-polling, no public
inbound port or webhook is required — only outbound internet.

## Local testing

`python test_agent.py` runs offline logic tests (JSON extraction / reply assembly).
With a real `.env`, `python test_agent.py --live "<question>"` runs the full agent
once and prints the reply.

The official grading harness is at
https://github.com/Jivraj-18/tds-p1-t2-2026-telegram-bot — clone it, add your own
questions to `evals/questions.json`, and point it at this bot to test end-to-end.
