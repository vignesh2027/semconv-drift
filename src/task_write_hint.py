# Task 4: Write with a version hint. The same 12 requests as Write, plus one
# sentence saying which spec version is current and that names have changed.
# The difference from Write measures how much a single line of context helps.
from dataclasses import dataclass

import kaggle_benchmarks as kbench
import pandas as pd

# Kaggle reserves quota for the maximum possible output of every call, so the
# cap keeps each reservation small. It is far above what an answer needs.
LIMITS = {"max_tokens": 6000}

HINT = (
    "Target OpenTelemetry semantic conventions v1.44.0 (released August 2026). Many attribute and metric "
    "names were renamed or removed between 2023 and 2026, so do not rely on older names. "
)

INSTRUCTIONS = HINT + (
    "Follow the current OpenTelemetry semantic conventions. Write attribute keys and metric names as "
    "string literals rather than SDK constants. Return one complete code block and nothing else."
)

CASES = [
    ("py_http_server", "Python", "Instrument this Flask route with an OpenTelemetry server span. Record the HTTP method, the route, the response status code, the client's address and the user agent.\n\n@app.route('/orders/<int:order_id>')\ndef get_order(order_id):\n    order = repo.find(order_id)\n    return jsonify(order), 200"),
    ("py_postgres", "Python", "Wrap this psycopg query in an OpenTelemetry client span. Record which database system it is, the database name, the operation, the table and the query text.\n\ndef list_orders(conn, customer_id):\n    with conn.cursor() as cur:\n        cur.execute('SELECT * FROM orders WHERE customer_id = %s', (customer_id,))\n        return cur.fetchall()"),
    ("go_http_client", "Go", "Instrument this outgoing HTTP call with an OpenTelemetry client span. Record the method, the full URL, the peer host name and port, and the response status code.\n\nfunc fetchQuote(ctx context.Context, url string) (*http.Response, error) {\n\treq, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)\n\treturn http.DefaultClient.Do(req)\n}"),
    ("go_redis", "Go", "Add an OpenTelemetry client span around this go-redis call. Record the database system, the command name, the full command text, and the Redis server host and port.\n\nfunc getSession(ctx context.Context, rdb *redis.Client, id string) (string, error) {\n\treturn rdb.Get(ctx, \"session:\"+id).Result()\n}"),
    ("ts_express", "TypeScript", "Instrument this Express handler with an OpenTelemetry server span. Record the HTTP method, the target path with query string, the scheme, the status code and the client IP address.\n\napp.get('/search', async (req, res) => {\n  const hits = await index.search(String(req.query.q))\n  res.status(200).json(hits)\n})"),
    ("ts_kafka", "TypeScript", "Instrument this kafkajs consumer with an OpenTelemetry consumer span per message. Record the messaging system, the topic, the partition, the message offset and the consumer group.\n\nawait consumer.run({\n  eachMessage: async ({topic, partition, message}) => {\n    await handle(message.value)\n  },\n})"),
    ("py_grpc", "Python", "Add an OpenTelemetry client span around this gRPC call. Record the RPC system, the service, the method and the gRPC status code.\n\ndef get_user(stub, user_id):\n    return stub.GetUser(users_pb2.GetUserRequest(id=user_id))"),
    ("go_http_metrics", "Go", "Add OpenTelemetry metrics to this HTTP middleware: a histogram of server request duration and a histogram of client request duration for outgoing calls. Use the standard metric names and units from the semantic conventions.\n\nfunc Middleware(next http.Handler) http.Handler {\n\treturn http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {\n\t\tnext.ServeHTTP(w, r)\n\t})\n}"),
    ("py_pool_metrics", "Python", "Add OpenTelemetry metrics for this database connection pool: the number of connections in use, the time spent waiting for a connection, and the time a connection is held. Use the standard metric names and units from the semantic conventions.\n\nclass Pool:\n    def acquire(self):\n        ...\n    def release(self, conn):\n        ..."),
    ("py_code_location", "Python", "Add an OpenTelemetry span to this function that records where it runs: the function name, the source file path and the line number.\n\ndef reconcile(ledger):\n    return sum(entry.amount for entry in ledger)"),
    ("ts_resource", "TypeScript", "Create an OpenTelemetry Resource for this service. It runs on an Azure virtual machine in the production environment. Record the service name 'billing', the deployment environment, the cloud provider and the cloud platform.\n\nimport {Resource} from '@opentelemetry/resources'"),
    ("go_peer_service", "Go", "Instrument this call to the payments service with an OpenTelemetry client span. Record the logical name of the remote service, the server address and port, and the HTTP method and status code.\n\nfunc charge(ctx context.Context, c *http.Client, body io.Reader) (*http.Response, error) {\n\treturn c.Post(\"http://payments:8080/charge\", \"application/json\", body)\n}"),
]


@kbench.task(store_task=False)
def write_hint_one(llm, case_id: str, language: str, request: str) -> dict:
    response = llm.prompt(f"Language: {language}.\n{request}\n\n{INSTRUCTIONS}", extra_api_params=LIMITS)
    found = audit(response)  # noqa: F821, from the inlined grader
    instrumented = len(found["current"]) + len(found["retired"]) + len(found["moved_out"]) + len(found["invented"]) >= 3
    return {
        "case": case_id,
        "retired": found["retired"],
        "retired_since": found["retired_since"],
        "invented": found["invented"],
        "unit_errors": found["unit_errors"],
        "current": found["current"],
        "instrumented": instrumented,
        "clean": instrumented and not found["retired"] and not found["invented"] and not found["unit_errors"],
    }


@kbench.task(
    name="Semconv Drift: Write with version hint",
    description="The 12 Write requests plus one sentence naming the current spec version and warning that names changed. Measures how much a single line of context reduces drift.",
)
def semconv_write_hint(llm) -> float:
    df = pd.DataFrame([{"case_id": c, "language": lang, "request": r} for c, lang, r in CASES])
    runs = write_hint_one.evaluate(
        llm=[llm],
        evaluation_data=df,
        stop_condition=lambda runs: len(runs) == len(df),
        max_attempts=3,
        n_jobs=1,
        timeout=240,
        on_failure="continue",
        remove_run_files=True,
    )
    rows = [r.result for r in runs if isinstance(getattr(r, "result", None), dict)]
    if len(rows) != len(df):
        # A case that never ran must not count as a model failure.
        raise RuntimeError(f"Only {len(rows)} of {len(df)} cases completed; not scoring a partial run.")
    retired_total = sum(len(r["retired"]) for r in rows)
    kbench.assertions.assert_true(
        retired_total == 0,
        expectation=f"No retired names in generated code (found {retired_total}: "
        + ", ".join(sorted({n for r in rows for n in r["retired"]}))
        + ")",
    )
    return round(sum(r["clean"] for r in rows) / len(CASES), 4)


semconv_write_hint.run(kbench.llm)
