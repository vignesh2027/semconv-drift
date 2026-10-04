# Task 2: Know. Does the model know what replaced a retired name, in context?
from dataclasses import dataclass

import kaggle_benchmarks as kbench
import pandas as pd


@dataclass
class Answer:
    current_name: str
    unit: str


INSTRUCTIONS = (
    "Answer for the current OpenTelemetry semantic conventions (v1.44.0). In current_name, give the name "
    "to use today; if it has not changed, repeat it; if two names replace it, give both separated by ' and '. "
    "In unit, give the UCUM unit for metrics (for example s or ms) and an empty string otherwise."
)

# (id, question, accepted answers, unit). Every gold answer is checked against
# the Attrition dataset by build.py before the task file is written.
QUESTIONS = [
    ("server_peer", "On an HTTP server span, which attribute replaces net.peer.name?", ["client.address"], ""),
    ("client_peer", "On an HTTP client span, which attribute replaces net.peer.name?", ["server.address"], ""),
    ("server_peer_port", "On an HTTP server span, which attribute replaces net.peer.port?", ["client.port"], ""),
    ("method", "Which attribute replaces http.method?", ["http.request.method"], ""),
    ("status", "Which attribute replaces http.status_code?", ["http.response.status_code"], ""),
    ("url", "Which attribute replaces http.url?", ["url.full"], ""),
    ("target", "Which attributes replace http.target?", ["url.path and url.query"], ""),
    ("user_agent", "Which attribute replaces http.user_agent?", ["user_agent.original"], ""),
    ("statement", "Which attribute replaces db.statement?", ["db.query.text"], ""),
    ("db_system", "Which attribute replaces db.system?", ["db.system.name"], ""),
    ("db_operation", "Which attribute replaces db.operation?", ["db.operation.name"], ""),
    ("filepath", "Which attribute replaces code.filepath?", ["code.file.path"], ""),
    ("lineno", "Which attribute replaces code.lineno?", ["code.line.number"], ""),
    ("deployment", "Which resource attribute replaces deployment.environment?", ["deployment.environment.name"], ""),
    ("peer_service", "Which attribute replaces peer.service?", ["service.peer.name"], ""),
    ("kafka_offset", "Which attribute replaces messaging.kafka.message.offset?", ["messaging.kafka.offset"], ""),
    ("resend", "Which attribute replaces http.resend_count?", ["http.request.resend_count"], ""),
    ("server_duration", "Which metric replaces http.server.duration, and what is its unit?", ["http.server.request.duration"], "s"),
    ("pool_use_time", "Which metric replaces db.client.connections.use_time, and what is its unit?", ["db.client.connection.use_time"], "s"),
    ("rpc_duration", "Which metric replaces rpc.client.duration, and what is its unit?", ["rpc.client.call.duration"], "s"),
    ("control_url_full", "Which attribute replaces url.full?", ["url.full"], ""),
    ("control_server_address", "Which attribute replaces server.address?", ["server.address"], ""),
]


def _names(text):
    return sorted(set(re.findall(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+", text.lower())))  # noqa: F821


@kbench.task(store_task=False)
def know_one(llm, qid: str, question: str, gold: list, unit: str) -> dict:
    answer = llm.prompt(f"{question}\n\n{INSTRUCTIONS}", schema=Answer)
    given = _names(answer.current_name)
    expected = sorted({n for g in gold for n in _names(g)})
    name_ok = given == expected
    unit_ok = (answer.unit or "").strip().lower() == unit
    retired_answer = [n for n in given if n in ATTR and is_retired(ATTR[n]) or n in METRIC and is_retired(METRIC[n])]  # noqa: F821
    return {
        "id": qid,
        "given": answer.current_name,
        "unit": answer.unit,
        "correct": name_ok and unit_ok,
        "answered_with_retired_name": bool(retired_answer),
        "control": qid.startswith("control_"),
    }


@kbench.task(
    name="Semconv Drift: Know",
    description="22 questions on what replaced a retired OpenTelemetry name, including span kind, unit changes, silent drops and two unchanged controls.",
)
def semconv_know(llm) -> float:
    df = pd.DataFrame([{"qid": q, "question": t, "gold": g, "unit": u} for q, t, g, u in QUESTIONS])
    runs = know_one.evaluate(
        llm=[llm],
        evaluation_data=df,
        stop_condition=lambda runs: len(runs) == len(df),
        max_attempts=2,
        n_jobs=6,
        timeout=120,
        on_failure="continue",
        remove_run_files=True,
    )
    rows = [r.result for r in runs if isinstance(getattr(r, "result", None), dict)]
    wrong = [r["id"] for r in rows if not r["correct"]]
    kbench.assertions.assert_true(not wrong, expectation="All answers correct (wrong: " + ", ".join(wrong) + ")")
    return round(sum(r["correct"] for r in rows) / len(QUESTIONS), 4)


semconv_know.run(kbench.llm)
