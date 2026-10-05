"""Prints what each model actually answered for one case: python3 show_answers.py fix enum_value [filter]"""
import glob
import json
import re
import sys

task, case = sys.argv[1], sys.argv[2]
pat = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None
best = {}
for f in glob.glob(f"results/runs/{task}/*/*/*/*/*.run.json"):
    version = int(f.split("/")[4])
    run = json.load(open(f))
    model = run["modelVersion"]["slug"].split("/")[-1]
    if model in best and best[model][0] >= version:
        continue
    for s in run.get("subruns") or []:
        res = json.dumps(s.get("results"))
        if f'"{case}"' not in res:
            continue
        answer = s["conversations"][-1]["requests"][-1]["contents"][-1]["parts"][-1].get("text", "")
        best[model] = (version, answer, res)
for model, (_, answer, res) in sorted(best.items()):
    lines = [l for l in answer.split("\n") if not pat or pat.search(l)]
    verdict = re.search(r'"(correct|clean)": (true|false)', res)
    print(f"--- {model}  [{verdict.group(0) if verdict else '?'}]")
    print("\n".join(lines[:8]))
