"""Downloads the newest run of every task for every model and summarises it.

Writes results/summary.json and results/report.md. Only the newest task
version is used for each task, and a run counts only when every case completed.
Usage: python3 analyze.py [--no-download]
"""
import collections
import datetime
import json
import math
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
KAGGLE = str(ROOT.parent / ".venv" / "bin" / "kaggle")
RUNS = ROOT / "results" / "runs"
TASKS = {
    "write": ("semconv-drift-write", 12),
    "know": ("semconv-drift-know", 22),
    "fix": ("semconv-drift-fix", 8),
    "hint": ("semconv-drift-write-with-version-hint", 12),
}
MAIN = ["write", "know", "fix"]
TODAY = datetime.date(2026, 10, 5)
PAIRS = [
    ("Claude Sonnet", "claude-sonnet-4-5", "claude-sonnet-5"),
    ("GPT", "gpt-5.4", "gpt-5.5"),
    ("Gemini Pro", "gemini-2.5-pro", "gemini-3.1-pro-preview"),
]
NAMES = {
    "claude-opus-5": "Claude Opus 5", "claude-sonnet-5": "Claude Sonnet 5", "claude-sonnet-4-5": "Claude Sonnet 4.5",
    "claude-haiku-4-5": "Claude Haiku 4.5", "gpt-6-astra": "GPT-6 Astra", "gpt-5.5": "GPT-5.5", "gpt-5.4": "GPT-5.4",
    "gpt-5.4-mini": "GPT-5.4 mini", "gpt-oss-120b": "gpt-oss-120b", "gemini-3.1-pro-preview": "Gemini 3.1 Pro",
    "gemini-2.5-pro": "Gemini 2.5 Pro", "gemini-3.8-flash": "Gemini 3.8 Flash", "gemini-3.7-flash": "Gemini 3.7 Flash",
    "gemma-4-31b": "Gemma 4 31B", "glm-5": "GLM-5", "deepseek-r1-0528": "DeepSeek-R1",
    "qwen3-235b-a22b-instruct-2507": "Qwen 3 235B", "grok-4.5-0708": "Grok 4.5", "grok-4.6": "Grok 4.6",
}


def short(slug):
    s = slug.split("/")[-1]
    s = re.sub(r"@.*$", "", s)
    s = re.sub(r"-20\d\d-\d\d-\d\d$", "", s)
    return s


def download():
    if "--no-download" in sys.argv:
        return
    for key, (slug, _) in TASKS.items():
        subprocess.run([KAGGLE, "benchmarks", "tasks", "download", slug, "-o", str(RUNS / key), "-f"], capture_output=True)


def latest_runs(key):
    best = {}
    for f in (RUNS / key).glob("*/*/*/*/*.run.json"):
        version = int(f.relative_to(RUNS / key).parts[1])
        run = json.loads(f.read_text())
        model = short(run["modelVersion"]["slug"])
        if model not in best or version > best[model][0]:
            best[model] = (version, run)
    return best


def cases(run):
    out = []
    for s in run.get("subruns") or []:
        for res in s.get("results", []):
            if "dictResult" in res:
                out.append(res["dictResult"])
    return out


def score(run):
    for res in run.get("results", []):
        if "numericResult" in res:
            return res["numericResult"].get("value", 0.0)  # Kaggle omits a 0 value
    return None


def cost_and_tokens(run):
    usd, out_tokens = 0.0, 0
    for s in run.get("subruns") or []:
        for conv in s.get("conversations") or []:
            m = conv.get("metrics", {})
            usd += (int(m.get("inputTokensCostNanodollars", 0)) + int(m.get("outputTokensCostNanodollars", 0))) / 1e9
            out_tokens += int(m.get("outputTokens", 0))
    return usd, out_tokens


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0, c - h), 3), round(min(1, c + h), 3))


def years_since(date):
    return round((TODAY - datetime.date.fromisoformat(date)).days / 365.25, 2)


def main():
    download()
    runs = {k: latest_runs(k) for k in TASKS}
    models = sorted(set().union(*[set(runs[k]) for k in MAIN]))
    board, matrix = [], {}
    retired_uses = collections.Counter()
    retired_models = collections.defaultdict(set)
    retired_meta = {}
    invented = collections.Counter()
    invented_models = collections.defaultdict(set)
    ages = []
    rpc_outcomes = {}
    quotes = collections.defaultdict(list)

    for m in models:
        row = {"model": m, "name": NAMES.get(m, m), "cost_usd": 0.0, "output_tokens": 0}
        complete = True
        for key in TASKS:
            entry = runs[key].get(m)
            if not entry:
                if key in MAIN:
                    complete = False
                continue
            version, run = entry
            cs = cases(run)
            n = TASKS[key][1]
            ok = len(cs) == n and score(run) is not None
            if key in MAIN:
                complete &= ok
            if not ok:
                continue
            usd, toks = cost_and_tokens(run)
            if key in MAIN:
                row["cost_usd"] += usd
                row["output_tokens"] += toks
            passed_field = {"write": "clean", "know": "correct", "fix": "correct", "hint": "clean"}[key]
            k = sum(1 for c in cs if c.get(passed_field))
            row[key] = round(k / n, 4)
            row[f"{key}_ci"] = wilson(k, n)
            row[f"{key}_version"] = version
            ident = {"write": "case", "know": "id", "fix": "case", "hint": "case"}[key]
            matrix.setdefault(key, {})[m] = {c[ident]: bool(c.get(passed_field)) for c in cs}
            if key in ("write", "hint"):
                row[f"{key}_retired"] = sum(len(c["retired"]) for c in cs)
                row[f"{key}_invented"] = sum(len(c.get("invented", [])) for c in cs)
            if key == "write":
                row["write_unit_errors"] = sum(len(c["unit_errors"]) for c in cs)
                for c in cs:
                    for name in c["retired"]:
                        retired_uses[name] += 1
                        retired_models[name].add(m)
                        since = c.get("retired_since", {}).get(name)
                        if since and since.get("date"):
                            retired_meta[name] = since
                            ages.append(years_since(since["date"]))
                    for name in c.get("invented", []):
                        invented[name] += 1
                        invented_models[name].add(m)
            if key == "know":
                by = {c["id"]: c for c in cs}
                row["know_controls_failed"] = [q for q in ("control_url_full", "control_server_address") if not by[q]["correct"]]
                row["know_retired_answers"] = sum(1 for c in cs if c["answered_with_retired_name"])
                for q in ("control_server_address", "control_url_full", "resend", "server_peer"):
                    if not by[q]["correct"]:
                        quotes[q].append((m, by[q]["given"]))
            if key == "fix":
                by = {c["case"]: c for c in cs}
                r = by["rpc_ms"]
                old_name = "rpc.client.duration" in r.get("retired_left", [])
                unit_bad = any("unit" in p for p in r.get("problems", [])) or any("milliseconds" in p for p in r.get("problems", []))
                if r["correct"]:
                    outcome = "correct"
                elif not old_name and not unit_bad and not r.get("missing") and not r.get("invented"):
                    outcome = "metric fixed, retired attributes added"
                elif old_name and not unit_bad:
                    outcome = "half fix: new unit, retired name"
                elif old_name:
                    outcome = "left unchanged"
                elif any(n.startswith("rpc.") for n in r.get("invented", [])):
                    outcome = "renamed to a name that does not exist"
                else:
                    outcome = "right name, values not converted"
                rpc_outcomes[m] = outcome
                row["fix_traps"] = {t: by[t]["correct"] for t in ("server_span", "enum_value", "rpc_ms", "go_redis_pool")}
        row["complete"] = complete
        if complete:
            row["overall"] = round(sum(row[k] for k in MAIN) / 3, 4)
        board.append(row)

    board.sort(key=lambda r: (-(r.get("overall") if r.get("overall") is not None else -1), r["model"]))
    done = [r for r in board if r["complete"]]
    graded = sum(TASKS[k][1] for k in MAIN) * len(done)
    summary = {
        "generated": TODAY.isoformat(),
        "models": len(models),
        "complete_models": len(done),
        "graded_answers_main": graded,
        "board": board,
        "matrix": matrix,
        "retired_names_in_write": [
            {"name": n, "uses": c, "models": len(retired_models[n]), **retired_meta.get(n, {})} for n, c in retired_uses.most_common()
        ],
        "retired_ages_years": ages,
        "invented_names_in_write": [{"name": n, "uses": c, "models": len(invented_models[n])} for n, c in invented.most_common()],
        "rpc_outcomes": rpc_outcomes,
        "know_wrong_quotes": quotes,
        "pairs": [
            {"family": fam, "older": a, "newer": b,
             "older_overall": next((r.get("overall") for r in board if r["model"] == a), None),
             "newer_overall": next((r.get("overall") for r in board if r["model"] == b), None)}
            for fam, a, b in PAIRS
        ],
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "summary.json").write_text(json.dumps(summary, indent=2))

    pct = lambda v: "n/a" if v is None else f"{v * 100:.0f}%"
    lines = ["| Model | Write | Know | Fix | Overall | Retired names written | Invented | Cost |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in board:
        lines.append(
            f"| {r['name']} | {pct(r.get('write'))} | {pct(r.get('know'))} | {pct(r.get('fix'))} | {pct(r.get('overall'))} | "
            f"{r.get('write_retired', 'n/a')} | {r.get('write_invented', 'n/a')} | ${r['cost_usd']:.2f} |"
        )
    (ROOT / "results" / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n{len(done)} of {len(models)} models complete on Write, Know and Fix; {graded} graded answers.")


if __name__ == "__main__":
    main()
