# Task 3: Fix. Can the model modernize old instrumentation without breaking it?
import kaggle_benchmarks as kbench
import pandas as pd

# Kaggle reserves quota for the maximum possible output of every call, so the
# cap keeps each reservation small. It is far above what an answer needs.
LIMITS = {"max_tokens": 6000}

INSTRUCTIONS = (
    "Update this code to the current OpenTelemetry semantic conventions (v1.44.0). Keep its behaviour "
    "correct: if a replacement changes a unit or a value format, convert the value too. Write attribute "
    "keys, metric names and attribute values as string literals rather than SDK constants. Return one "
    "complete code block and nothing else."
)

# (id, language, code, names that must appear, extra check). Traps:
#   server_span: net.peer.name on a SERVER span becomes client.address, not server.address.
#   go_redis_pool: real code from redis/go-redis records ms; the new metrics are in seconds.
#   rpc_ms: same unit trap for rpc.client.duration.
#   enum_value: the key is current, only the value is retired.
CASES = [
    ("http_client", "Python", """with tracer.start_as_current_span("GET /quote", kind=SpanKind.CLIENT) as span:
    span.set_attribute("http.method", "GET")
    span.set_attribute("http.url", url)
    span.set_attribute("net.peer.name", host)
    span.set_attribute("http.status_code", resp.status_code)""",
     ["http.request.method", "url.full", "server.address", "http.response.status_code"], None),
    ("server_span", "TypeScript", """tracer.startActiveSpan('POST /checkout', {kind: SpanKind.SERVER}, (span) => {
  span.setAttribute('http.method', req.method)
  span.setAttribute('net.peer.name', req.socket.remoteAddress)
  span.setAttribute('http.status_code', 200)
  span.end()
})""",
     ["http.request.method", "client.address", "http.response.status_code"], "not_server_address"),
    ("db_span", "Go", """span.SetAttributes(
	attribute.String("db.system", "postgresql"),
	attribute.String("db.statement", query),
	attribute.String("db.operation", "SELECT"),
)""",
     ["db.system.name", "db.query.text", "db.operation.name"], None),
    ("code_location", "Python", """span.set_attribute("code.filepath", __file__)
span.set_attribute("code.lineno", frame.f_lineno)""",
     ["code.file.path", "code.line.number"], None),
    ("resource", "TypeScript", """const resource = new Resource({
  'service.name': 'billing',
  'deployment.environment': 'production',
})""",
     ["deployment.environment.name"], None),
    ("enum_value", "Python", """resource = Resource.create({"cloud.provider": "azure", "cloud.platform": "azure_vm"})""",
     ["cloud.platform"], "value_azure_vm"),
    ("rpc_ms", "Go", """dur, _ := meter.Float64Histogram("rpc.client.duration", metric.WithUnit("ms"))
start := time.Now()
err := invoker(ctx, method, req, reply, cc, opts...)
dur.Record(ctx, float64(time.Since(start).Milliseconds()))""",
     ["rpc.client.call.duration"], "seconds"),
    ("go_redis_pool", "Go", """createTime, _ := conf.meter.Float64Histogram(
	"db.client.connections.create_time",
	metric.WithDescription("The time it took to create a new connection."),
	metric.WithUnit("ms"),
)
start := time.Now()
conn, err := dial(ctx)
createTime.Record(ctx, milliseconds(time.Since(start)))""",
     ["db.client.connection.create_time"], "seconds"),
]

_SECONDS_CONVERSION = re.compile(  # noqa: F821
    r"\.Seconds\(\)|/\s*1000(\.0)?\b|/\s*1e3\b|\*\s*0?\.001\b|/\s*float64\(time\.Second\)|seconds\(", re.I  # noqa: F821
)


@kbench.task(store_task=False)
def fix_one(llm, case_id: str, language: str, code: str, required: list, check: str) -> dict:
    response = llm.prompt(f"Language: {language}.\n\n```\n{code}\n```\n\n{INSTRUCTIONS}", extra_api_params=LIMITS)
    out = code_blocks(response)  # noqa: F821
    found = audit(out)  # noqa: F821
    names = {n for n in found["current"]}
    missing = [n for n in required if n not in names]
    problems = []
    if check == "not_server_address" and "server.address" in names:
        problems.append("used server.address on a server span")
    if check == "value_azure_vm" and not re.search(r"""["']azure\.vm["']""", out):  # noqa: F821
        problems.append("kept the retired value azure_vm")
    if check == "seconds":
        unit = re.search(r"""(?i)WithUnit\(\s*["']([^"']+)["']""", out)  # noqa: F821
        if not unit or unit.group(1) != "s":
            problems.append("metric unit is not s")
        if not _SECONDS_CONVERSION.search(out):
            problems.append("values still recorded in milliseconds")
    ok = not found["retired"] and not found["invented"] and not missing and not problems and not found["unit_errors"]
    return {"case": case_id, "retired_left": found["retired"], "retired_since": found["retired_since"], "invented": found["invented"], "missing": missing, "problems": problems + found["unit_errors"], "correct": ok}


@kbench.task(
    name="Semconv Drift: Fix",
    description="Modernizes 8 snippets of old OpenTelemetry code, with traps for span kind, retired enum values and metrics whose unit changed from ms to s.",
)
def semconv_fix(llm) -> float:
    df = pd.DataFrame([{"case_id": c, "language": lang, "code": code, "required": req, "check": chk or ""} for c, lang, code, req, chk in CASES])
    runs = fix_one.evaluate(
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
    wrong = [r["case"] for r in rows if not r["correct"]]
    kbench.assertions.assert_true(not wrong, expectation="Every snippet fully modernized (failed: " + ", ".join(wrong) + ")")
    return round(sum(r["correct"] for r in rows) / len(CASES), 4)


semconv_fix.run(kbench.llm)
