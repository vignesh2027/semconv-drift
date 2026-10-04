"""Checks the grader against code with known answers. Run: python3 test_grader.py"""
import pathlib

ns = {}
src = pathlib.Path(__file__).parent / "src"
exec("import json\nimport re\nDATA_JSON = " + repr((src / "semconv.json").read_text()) + "\n" + (src / "grader.py").read_text(), ns)
audit = ns["audit"]


def check(name, code, retired=(), current=(), units=0):
    got = audit(code)
    assert sorted(got["retired"]) == sorted(retired), (name, "retired", got["retired"])
    for c in current:
        assert c in got["current"], (name, "missing current", c, got["current"])
    assert len(got["unit_errors"]) == units, (name, "units", got["unit_errors"])
    print("ok", name)


check("old python strings", 'span.set_attribute("http.method", "GET")\nspan.set_attribute("db.statement", q)', retired=["db.statement", "http.method"])
check("new python strings", 'span.set_attribute("http.request.method", "GET")\nspan.set_attribute("server.address", h)', current=["http.request.method", "server.address"])
check("js constants", "span.setAttribute(SEMATTRS_HTTP_METHOD, m)\nspan.setAttribute(ATTR_HTTP_REQUEST_METHOD, m)", retired=["http.method"], current=["http.request.method"])
check("go constants", "semconv.HTTPMethodKey.String(m)\nsemconv.DBSystemNameKey.String(x)", retired=["http.method"], current=["db.system.name"])
check("python class", "span.set_attribute(SpanAttributes.DB_STATEMENT, q)", retired=["db.statement"])
check("comments ignored", '# old name was "http.method"\nspan.set_attribute("http.request.method", m)', current=["http.request.method"])
check("dropped metric", 'h = meter.create_histogram("http.server.duration", unit="ms")', retired=["http.server.duration"])
check("unit error", 'h = meter.create_histogram("http.server.request.duration", unit="ms")', current=["http.server.request.duration"], units=1)
check("unit ok", 'h, _ := meter.Float64Histogram("http.server.request.duration", metric.WithUnit("s"))', current=["http.server.request.duration"])
check("multiline unit", 'h, _ := meter.Float64Histogram(\n  "db.client.connection.wait_time",\n  metric.WithDescription("x"),\n  metric.WithUnit("ms"),\n)', current=["db.client.connection.wait_time"], units=1)
check("moved out not retired", 'span.set_attribute("gen_ai.request.model", "x")', retired=[])
check("fenced block", 'Here:\n```python\nspan.set_attribute("http.url", u)\n```\nDone, I avoided "db.system".', retired=["http.url"])
print("all grader checks passed")

got = audit("span = tracer.start_span('kafka.consume', attributes={'messaging.destination': t, 'messaging.system': 'kafka', 'acme.order_id': 1})")
assert got["invented"] == ["messaging.destination"], got
assert "messaging.system" in got["current"], got
got = audit('h = meter.create_histogram(\n    name="db.client.connections.in_use",\n    unit="connections",\n)')
assert got["invented"] == ["db.client.connections.in_use"] and not got["unit_errors"], got
got = audit('span.set_attribute("http.request.method", m)  # custom: "orders.total"')
assert got["invented"] == [], got
print("invented-name checks passed")
