"""Draws the charts for the write-up from results/summary.json into results/charts/."""
import collections
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "results" / "charts"
OUT.mkdir(parents=True, exist_ok=True)
S = json.loads((ROOT / "results" / "summary.json").read_text())

INK, MUTED, GRID = "#1b2333", "#6b7385", "#e6e8ee"
GOOD, BAD, WARN, ACCENT = "#1f9d68", "#d64545", "#e8a33d", "#3b6fd8"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12, "axes.edgecolor": GRID, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": INK, "axes.titleweight": "bold", "axes.titlesize": 15,
    "axes.titlecolor": INK, "figure.facecolor": "white", "axes.facecolor": "white", "savefig.dpi": 160,
})

board = [r for r in S["board"] if r["complete"]]
NAME = {r["model"]: r["name"] for r in S["board"]}


def finish(fig, ax, name, note=None):
    ax.spines[["top", "right"]].set_visible(False)
    if note:
        fig.text(0.01, 0.01, note, color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.03 if note else 0, 1, 1))
    fig.savefig(OUT / name, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("saved", name)


# 1. Leaderboard: overall with each task as a dot.
fig, ax = plt.subplots(figsize=(11, 0.48 * len(board) + 1.6))
rows = list(reversed(board))
y = range(len(rows))
ax.barh(y, [r["overall"] * 100 for r in rows], color="#dbe5fb", height=0.7, label="Overall")
for key, color, marker, dy in (("write", ACCENT, "o", 0.2), ("know", GOOD, "s", 0), ("fix", WARN, "D", -0.2)):
    ax.scatter([r[key] * 100 for r in rows], [i + dy for i in y], color=color, marker=marker, s=46, zorder=3, label=key.capitalize())
for i, r in enumerate(rows):
    ax.text(108, i, f"{r['overall'] * 100:.0f}%", va="center", ha="right", color=INK, fontsize=10, fontweight="bold")
ax.text(108, len(rows) - 0.3, "Overall", ha="right", color=MUTED, fontsize=9)
ax.set_yticks(list(y), [r["name"] for r in rows])
ax.set_xlim(0, 109)
ax.set_xlabel("Score (%)")
ax.grid(axis="x", color=GRID)
ax.set_axisbelow(True)
ax.legend(loc="lower right", frameon=False, ncol=4)
ax.set_title("Semconv Drift leaderboard: Write, Know and Fix")
finish(fig, ax, "01_leaderboard.png", f"{S['graded_answers_main']} graded answers, deterministic grading against 1,563 names from 26 spec releases.")

# 2. Heatmap of every case.
order = [r["model"] for r in board]
cols, labels = [], []
for key in ("write", "know", "fix"):
    ids = list(S["matrix"][key][order[0]].keys())
    cols += [(key, i) for i in ids]
    labels += [f"{key[0].upper()}: {i}" for i in ids]
grid = [[1 if S["matrix"][k][m].get(i) else 0 for k, i in cols] for m in order]
fig, ax = plt.subplots(figsize=(18, 0.42 * len(order) + 3.2))
ax.imshow(grid, aspect="auto", cmap=ListedColormap(["#f6c9c9", "#bfe6d3"]))
ax.set_yticks(range(len(order)), [NAME[m] for m in order])
ax.set_xticks(range(len(labels)), labels, rotation=90, fontsize=8)
for x in (12 - 0.5, 34 - 0.5):
    ax.axvline(x, color=INK, lw=1.5)
ax.set_title("Every case, every model (green = correct, red = wrong)")
finish(fig, ax, "02_heatmap.png")

# 3. How old are the retired names models still write?
ages = S["retired_ages_years"]
fig, ax = plt.subplots(figsize=(11, 5))
bins = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]
ax.hist(ages, bins=bins, color=BAD, edgecolor="white")
ax.set_xlabel("Years since the spec retired the name (as of 6 Oct 2026)")
ax.set_ylabel("Uses in generated code")
older = sum(1 for a in ages if a >= 1)
ax.set_title(f"{older} of {len(ages)} retired names written were retired more than a year ago")
ax.grid(axis="y", color=GRID)
ax.set_axisbelow(True)
finish(fig, ax, "03_retired_age.png", "v1.21.0 (July 2023) is the oldest release scanned, so the 3+ year bar means 'July 2023 or earlier'.")

# 4. Most used retired names, coloured by retirement year.
top = S["retired_names_in_write"][:14]
fig, ax = plt.subplots(figsize=(11, 6.5))
year_color = {"2023": "#7a1f1f", "2024": BAD, "2025": WARN, "2026": "#f1cf8e"}
names = [t["name"] for t in reversed(top)]
vals = [t["uses"] for t in reversed(top)]
colors = [year_color.get((t.get("date") or "2026")[:4], MUTED) for t in reversed(top)]
ax.barh(names, vals, color=colors)
for i, t in enumerate(reversed(top)):
    ax.text(t["uses"] + 0.2, i, f"{t['models']} models, retired {t.get('release')} ({(t.get('date') or '')[:7]})", va="center", fontsize=9, color=MUTED)
ax.set_xlabel("Uses across all models in the Write task")
ax.set_title("The retired names models reach for")
ax.set_xlim(0, max(vals) * 1.9)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in year_color.values()]
ax.legend(handles, [f"retired {y}" for y in year_color], frameon=False, loc="lower right")
finish(fig, ax, "04_top_retired_names.png")

# 5. Generation pairs.
pairs = [p for p in S["pairs"] if p["older_overall"] is not None and p["newer_overall"] is not None]
fig, ax = plt.subplots(figsize=(10, 3 + 0.6 * len(pairs)))
for i, p in enumerate(pairs):
    a, b = p["older_overall"] * 100, p["newer_overall"] * 100
    ax.plot([a, b], [i, i], color=GRID, lw=6, zorder=1)
    ax.scatter([a], [i], color=MUTED, s=90, zorder=2)
    ax.scatter([b], [i], color=GOOD, s=90, zorder=2)
    ax.text(a, i + 0.22, f"{NAME[p['older']]}\n{a:.0f}%", ha="center", fontsize=9, color=MUTED)
    ax.text(b, i - 0.42, f"{NAME[p['newer']]}\n{b:.0f}%", ha="center", fontsize=9, color=GOOD)
ax.set_yticks(range(len(pairs)), [p["family"] for p in pairs])
ax.set_xlim(0, 100)
ax.set_ylim(-0.8, len(pairs) - 0.2)
ax.set_xlabel("Overall score (%)")
ax.set_title("Each newer generation drifts less")
finish(fig, ax, "05_generations.png")

# 6. The half fix on the RPC metric.
out = S["rpc_outcomes"]
cats = ["correct", "metric fixed, retired attributes added", "half fix: new unit, retired name", "renamed to a name that does not exist", "right name, values not converted", "left unchanged"]
cat_color = {cats[0]: GOOD, cats[1]: "#7cc9a5", cats[2]: WARN, cats[3]: "#8e6bd6", cats[4]: "#c98a2a", cats[5]: BAD}
counts = collections.Counter(out.values())  # every model with a Fix result
fig, ax = plt.subplots(figsize=(11, 2.9))
left = 0
for c in cats:
    n = counts.get(c, 0)
    if n:
        ax.barh([0], [n], left=left, color=cat_color[c], edgecolor="white")
        ax.text(left + n / 2, 0, f"{n}", ha="center", va="center", color="white", fontsize=13, fontweight="bold")
        left += n
ax.set_yticks([])
ax.set_xlim(0, len(out))
ax.legend([plt.Rectangle((0, 0), 1, 1, color=cat_color[c]) for c in cats if counts.get(c)], [c for c in cats if counts.get(c)], frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=3, fontsize=10)
ax.set_title("Fixing rpc.client.duration (ms): most models fixed the unit and kept the retired name")
finish(fig, ax, "06_half_fix.png", f"{len(out)} models with a Fix result. The half fix records seconds under a name the old spec defined in milliseconds, so it matches neither version.")

# 7. Cost against score.
fig, ax = plt.subplots(figsize=(10, 6))
for r in board:
    ax.scatter(r["cost_usd"], r["overall"] * 100, s=80, color=ACCENT, zorder=3)
    ax.annotate(r["name"], (r["cost_usd"], r["overall"] * 100), textcoords="offset points", xytext=(6, 4), fontsize=9, color=INK)
ax.set_xscale("symlog", linthresh=0.05)
ax.set_xlabel("Model cost for all 42 cases (USD, Kaggle usage metering)")
ax.set_ylabel("Overall score (%)")
ax.grid(color=GRID)
ax.set_axisbelow(True)
ax.set_title("Price is a weak guide to drift")
finish(fig, ax, "07_cost_vs_score.png")

# 8. Version hint effect.
hint = [r for r in board if r.get("hint") is not None]
if hint:
    hint.sort(key=lambda r: r["write"])
    fig, ax = plt.subplots(figsize=(10, 0.5 * len(hint) + 1.8))
    for i, r in enumerate(hint):
        a, b = r["write"] * 100, r["hint"] * 100
        ax.annotate("", xy=(b, i), xytext=(a, i), arrowprops=dict(arrowstyle="->", color=GOOD if b > a else BAD if b < a else MUTED, lw=2))
        ax.scatter([a], [i], color=MUTED, s=40, zorder=3)
    ax.set_yticks(range(len(hint)), [r["name"] for r in hint])
    ax.set_xlim(-2, 102)
    ax.set_xlabel("Write score (%): without hint (grey dot) to with one-sentence version hint (arrow)")
    ax.grid(axis="x", color=GRID)
    ax.set_title("What one sentence of context changes")
    finish(fig, ax, "08_version_hint.png")

# 9. Invented names.
inv = S["invented_names_in_write"][:10]
if inv:
    fig, ax = plt.subplots(figsize=(10, 0.45 * len(inv) + 1.6))
    ax.barh([i["name"] for i in reversed(inv)], [i["uses"] for i in reversed(inv)], color="#8e6bd6")
    ax.set_xlabel("Uses in the Write task")
    ax.set_title("Names no version of the spec ever defined")
    finish(fig, ax, "09_invented_names.png", "Keys under a namespace the spec owns (messaging., db., ...) that no release from v1.0.0 to v1.44.0 defined.")

# 10. Knew it, wrote it anyway.
kbw = S.get("knew_but_wrote", {})
rows = sorted([r for r in board if r["model"] in kbw], key=lambda r: r.get("knew_but_wrote", 0))
if rows:
    fig, ax = plt.subplots(figsize=(10, 0.45 * len(rows) + 1.8))
    vals = [r.get("knew_but_wrote", 0) for r in rows]
    ax.barh([r["name"] for r in rows], vals, color=[BAD if v else GOOD for v in vals])
    for i, r in enumerate(rows):
        names = ", ".join(b["name"] for b in kbw[r["model"]][:3]) + (" ..." if len(kbw[r["model"]]) > 3 else "")
        ax.text(vals[i] + 0.15, i, names or "none", va="center", fontsize=9, color=MUTED)
    ax.set_xlim(0, max(vals) * 2.4 + 1)
    ax.set_xlabel("Retired names written in Write that the same model correctly replaced in Know")
    n = sum(1 for v in vals if v)
    ax.set_title(f"{n} of {len(rows)} models knew the new name and wrote the old one anyway")
    finish(fig, ax, "10_knew_but_wrote.png", "Same model, same name: asked directly it gives the current name; asked to write code it uses the retired one.")

# Cover image for the DEV post (1000 x 420).
fig = plt.figure(figsize=(10, 4.2), dpi=200)
fig.patch.set_facecolor("#0e131d")
fig.text(0.05, 0.80, "SEMCONV DRIFT", color="#6d97f0", fontsize=13, fontweight="bold")
fig.text(0.05, 0.60, "AI models still write OpenTelemetry", color="white", fontsize=25, fontweight="bold")
fig.text(0.05, 0.47, "names the spec retired years ago", color="white", fontsize=25, fontweight="bold")
fig.text(0.05, 0.31, 'attribute.String("db.system", "redis")', color="#f07272", fontsize=15, family="DejaVu Sans Mono")
fig.text(0.05, 0.22, 'retired in v1.30.0; the current name is db.system.name', color="#98a1b4", fontsize=11)
fig.text(0.05, 0.07, f"{sum(1 for r in S['board'] if r.get('write') is not None)} models  ·  4 Kaggle tasks  ·  1,563 names from 26 spec releases  ·  no AI judge",
         color="#98a1b4", fontsize=11)
fig.savefig(OUT / "00_cover.png", facecolor=fig.get_facecolor())
plt.close(fig)
print("saved 00_cover.png")
