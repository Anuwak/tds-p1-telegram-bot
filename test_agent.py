"""Tests for the bot.

Offline (default): validates JSON extraction and reply assembly with no network.
Live:  python test_agent.py --live "your data-analysis question here"
       runs the full agent once using your real .env and prints the reply.
"""
import os
import sys

# Ensure imports succeed even without a real .env for the offline logic tests.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy")
os.environ.setdefault("LLM_API_KEY", "dummy")

import bot  # noqa: E402
import agent  # noqa: E402


def test_offline():
    # 1. plain JSON object
    o = bot.extract_json_object('{"answer": {"state": "Assam"}, "log_url": "LOG_URL_PLACEHOLDER"}')
    assert o == {"answer": {"state": "Assam"}, "log_url": "LOG_URL_PLACEHOLDER"}, o

    # 2. fenced + prose around it
    o = bot.extract_json_object('Here is the answer:\n```json\n{"answer": 42, "log_url": "LOG_URL_PLACEHOLDER"}\n```')
    assert o == {"answer": 42, "log_url": "LOG_URL_PLACEHOLDER"}, o

    # 3. nested braces / strings with braces
    o = bot.extract_json_object('{"answer": {"note": "a {b} c"}, "log_url": "x"}')
    assert o == {"answer": {"note": "a {b} c"}, "log_url": "x"}, o

    # 4. reply assembly substitutes the placeholder and enforces log_url
    reply = bot.build_reply('{"answer": {"state": "Assam"}, "log_url": "LOG_URL_PLACEHOLDER"}',
                            "https://example.com/run-1.jsonl")
    assert reply == '{"answer": {"state": "Assam"}, "log_url": "https://example.com/run-1.jsonl"}', reply

    # 5. model forgot log_url -> we add it
    reply = bot.build_reply('{"answer": 7}', "https://example.com/l.jsonl")
    import json
    assert json.loads(reply) == {"answer": 7, "log_url": "https://example.com/l.jsonl"}, reply

    # 6. total garbage -> still valid JSON
    reply = bot.build_reply('no json here', "https://example.com/l.jsonl")
    assert json.loads(reply)["log_url"] == "https://example.com/l.jsonl"

    print("offline tests: PASS")


def test_live(question):
    import config, log_store
    print(f"Model={config.LLM_MODEL}  base={config.LLM_BASE_URL}")
    log = []
    final = agent.solve([question], log)
    print("\n--- FINAL (raw) ---\n", final)
    url = log_store.publish(log)
    print("\n--- LOG URL ---\n", url)
    print("\n--- REPLY ---\n", bot.build_reply(final, url))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--live":
        test_live(sys.argv[2])
    else:
        test_offline()
