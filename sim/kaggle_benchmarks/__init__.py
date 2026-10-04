"""A tiny local stand-in for kaggle_benchmarks, used only to dry-run the task
files before pushing them. It calls models through the Groq API."""
import dataclasses
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

MODEL = os.environ.get("SIM_MODEL", "openai/gpt-oss-120b")
RESULTS = []


class _LLM:
    def __init__(self, model):
        self.model = model

    def prompt(self, text, schema=str, temperature=0):
        if schema is not str:
            fields = [f.name for f in dataclasses.fields(schema)]
            text += "\n\nReply with only a JSON object with these string keys: " + ", ".join(fields)
        body = json.dumps({"model": self.model, "temperature": temperature, "messages": [{"role": "user", "content": text}]}).encode()
        for attempt in range(6):
            try:
                req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", body, {"Authorization": "Bearer " + os.environ["GROQ_API_KEY"], "Content-Type": "application/json", "User-Agent": "sim"})
                out = json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"]
                break
            except Exception as e:  # rate limits on the free tier
                import time
                time.sleep(15 * (attempt + 1))
        if schema is str:
            return out
        m = re.search(r"\{.*\}", out, re.S)
        data = json.loads(m.group(0)) if m else {}
        return schema(**{f: str(data.get(f, "")) for f in [x.name for x in dataclasses.fields(schema)]})


llm = _LLM(MODEL)


class _Run:
    def __init__(self, result):
        self.result = result


class _Task:
    def __init__(self, fn):
        self.fn = fn

    def evaluate(self, llm, evaluation_data, n_jobs=1, **kw):
        rows = evaluation_data.to_dict("records")
        with ThreadPoolExecutor(2) as ex:
            return [_Run(r) for r in ex.map(lambda row: self.fn(llm[0], **row), rows)]

    def run(self, llm, *a, **k):
        result = self.fn(llm, *a, **k)
        RESULTS.append(result)
        print("SCORE", result)
        return result


def task(*a, **k):
    if a and callable(a[0]):
        return _Task(a[0])
    return lambda fn: _Task(fn)


class assertions:
    @staticmethod
    def assert_true(expr, expectation=None):
        print("ASSERT", "pass" if expr else "FAIL", "|", expectation)
