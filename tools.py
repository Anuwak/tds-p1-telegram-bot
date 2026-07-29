"""Execution tools available to the agent.

The main tool is `run_python`: it executes Python code in a subprocess whose
working directory is shared across all steps of a single run, so files the
agent downloads or writes (CSVs, parquet, JSON) persist between steps. In-memory
variables do NOT persist, so the agent is told to save intermediate data to disk
and reload it when needed.
"""
import subprocess
import sys
import tempfile
import os
import textwrap

import config


class RunWorkspace:
    """A per-run temp directory that persists files across run_python calls."""

    def __init__(self):
        self._dir = tempfile.mkdtemp(prefix="agent_run_")

    @property
    def path(self) -> str:
        return self._dir

    def run_python(self, code: str) -> dict:
        """Execute `code` in the workspace dir. Returns {ok, stdout, stderr}."""
        script_path = os.path.join(self._dir, "_step.py")
        # A small preamble that makes common libs available and prints nicely.
        preamble = textwrap.dedent(
            """
            import warnings, os, sys, json
            warnings.filterwarnings("ignore")
            try:
                import pandas as pd
                pd.set_option("display.max_columns", 50)
                pd.set_option("display.width", 200)
            except Exception:
                pass
            """
        )
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(preamble + "\n" + code)
        try:
            proc = subprocess.run(
                [sys.executable, script_path],
                cwd=self._dir,
                capture_output=True,
                text=True,
                timeout=config.PYTHON_TIMEOUT,
            )
            out = proc.stdout or ""
            err = proc.stderr or ""
            # Truncate very long output so we don't blow the LLM context.
            out = _truncate(out, 12000)
            err = _truncate(err, 6000)
            return {"ok": proc.returncode == 0, "stdout": out, "stderr": err}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": f"TIMEOUT after {config.PYTHON_TIMEOUT}s"}
        except Exception as e:  # pragma: no cover
            return {"ok": False, "stdout": "", "stderr": f"execution error: {e}"}


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    half = limit // 2
    return s[:half] + f"\n...[truncated {len(s) - limit} chars]...\n" + s[-half:]


# The tool schema exposed to the LLM (OpenAI function-calling format).
TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Execute Python 3 code to fetch, parse and analyse data. "
                "pandas, numpy, requests, bs4 (BeautifulSoup), lxml and openpyxl are installed. "
                "The working directory persists across calls within this task, so files you save "
                "(e.g. df.to_csv('data.csv')) are available in later calls, but in-memory variables are NOT. "
                "Always print() the values you need to inspect. Use this to download datasets from URLs in the "
                "question, clean them, and compute the final answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python code to run."}
                },
                "required": ["code"],
            },
        },
    }
]
