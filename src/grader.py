# Deterministic grading for the semconv drift benchmark.
#
# DATA holds every OpenTelemetry semantic convention name from 26 releases
# (v1.21.0 to v1.44.0), exported from the public Attrition dataset in Sanity
# (project y9raau23). Each entry: kind (a/m/e), status (c current, d
# deprecated, x dropped), verdict, replacement names, unit for metrics, and
# deprecated enum values with their replacement.
#
# No model is used for grading. Every score is reproducible from this file.
import json
import re

INDEX = json.loads(DATA_JSON)  # noqa: F821, injected by build.py

ATTR = {}
METRIC = {}
EVENT = {}
for row in INDEX:
    {"a": ATTR, "m": METRIC, "e": EVENT}[row["k"]][row["n"]] = row

# Retired means the spec tells you to stop using the name. Names that moved to
# the GenAI repository are still valid there, so they are reported apart.
RETIRED = {"d", "x"}


def is_retired(row):
    return row["s"] in RETIRED and row.get("v") != "MOVED_OUT"


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Namespaces the specification owns. A key under one of these that the spec
# does not define is invented (or older than v1.21.0); custom keys outside
# them, such as app.order_id, are allowed by OpenTelemetry and never counted.
OWNED = {n.split(".")[0] for n in list(ATTR) + list(METRIC) + list(EVENT)}

_BY_NORM = {}
for _key in ATTR:
    _BY_NORM.setdefault(_norm(_key), []).append(_key)

_LITERAL = re.compile(r"""["'`]([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)["'`]""")
_CONSTANTS = [
    (re.compile(r"\b(?:ATTR|SEMATTRS|SEMRESATTRS|METRIC)_([A-Z0-9_]+)\b"), False),
    (re.compile(r"\b\w*(?:Attributes|Attrs)\.([A-Z][A-Z0-9_]+)\b"), False),
    (re.compile(r"\bsemconv\.([A-Z][A-Za-z0-9]+)\b"), True),
]
_METRIC_CALL = re.compile(r"(?i)histogram|counter|gauge|meter|instrument")
# A dotted literal used as an attribute key or a metric name.
_D = r"""["'`]([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)["'`]"""
_KEY_CONTEXT = [
    re.compile(_D + r"\s*:"),  # {"http.method": ...}
    re.compile(r"(?i)set_?attributes?\(\s*" + _D),  # set_attribute("x", ...), setAttribute('x', ...)
    re.compile(r"\battribute\.\w+\(\s*" + _D),  # Go attribute.String("x", ...)
    re.compile(r"(?i)(?:histogram|counter|gauge|create_\w+)\(\s*(?:name\s*=\s*)?" + _D),
    re.compile(r"\bname\s*=\s*" + _D),  # create_histogram(\n  name="x")
]
_TIME_UNITS = {"ns", "us", "ms", "s", "min", "h"}
_UNIT = re.compile(r"""(?i)unit\s*[:=(]\s*["']([^"']+)["']|WithUnit\(\s*["']([^"']+)["']""")


def _strip_comments(code):
    out = []
    for line in code.split("\n"):
        t = line.lstrip()
        if t.startswith(("//", "#", "*", "/*")):
            continue
        out.append(re.sub(r"\s(//|#)\s.*$", "", line))
    return "\n".join(out)


def code_blocks(text):
    """The code a model returned: fenced blocks if any, otherwise the text."""
    blocks = re.findall(r"```[\w+-]*\n(.*?)```", text, re.S)
    return "\n".join(blocks) if blocks else text


def extract(code):
    """Semconv names used in code, as {(kind, name)}, plus metric units."""
    code = _strip_comments(code)
    names = set()
    units = {}
    keys = set()
    for rx in _KEY_CONTEXT:
        keys.update(m.group(1) for m in rx.finditer(code))
    for line in code.split("\n"):
        for m in _LITERAL.finditer(line):
            name = m.group(1)
            if name in METRIC and (name not in ATTR or _METRIC_CALL.search(line)):
                names.add(("m", name))
                u = _UNIT.search(line)
                if u:
                    units[name] = u.group(1) or u.group(2)
            elif name in EVENT and name not in ATTR:
                names.add(("e", name))
            elif name in ATTR:
                names.add(("a", name))
        for rx, go_style in _CONSTANTS:
            for m in rx.finditer(line):
                raw = m.group(1)
                if go_style:
                    raw = re.sub(r"Key$", "", raw)
                matches = _BY_NORM.get(_norm(raw))
                if matches and len(matches) == 1:
                    names.add(("a", matches[0]))
    # A unit on the following lines (multi-line builder calls).
    for name in [n for k, n in names if k == "m" and n not in units]:
        i = code.find(name)
        u = _UNIT.search(code[i : i + 400]) if i >= 0 else None
        if u:
            units[name] = u.group(1) or u.group(2)
    invented = sorted(
        k for k in keys
        if k.split(".")[0] in OWNED and k not in ATTR and k not in METRIC and k not in EVENT
    )
    return names, units, invented


def _lookup(kind, name):
    return {"a": ATTR, "m": METRIC, "e": EVENT}[kind].get(name)


def audit(code):
    """Retired names, moved names, unit errors and current names in code."""
    names, units, invented = extract(code_blocks(code))
    retired, moved, current = [], [], []
    for kind, name in sorted(names):
        row = _lookup(kind, name)
        if row is None:
            continue
        if is_retired(row):
            retired.append(name)
        elif row.get("v") == "MOVED_OUT":
            moved.append(name)
        else:
            current.append(name)
    unit_errors = []
    for name, unit in units.items():
        row = METRIC.get(name)
        spec_unit = row.get("u") if row else None
        if row and row["s"] == "c" and spec_unit in _TIME_UNITS and unit in _TIME_UNITS and unit != spec_unit:
            unit_errors.append(f"{name} in {unit}, spec says {row['u']}")
    return {
        "retired": retired,
        "moved_out": moved,
        "current": current,
        "invented": invented,
        "unit_errors": unit_errors,
    }


def replacement_of(name, kind="a"):
    row = _lookup(kind, name)
    return row.get("r", []) if row else []
