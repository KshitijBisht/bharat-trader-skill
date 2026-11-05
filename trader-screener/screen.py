#!/usr/bin/env python3
"""The Stock Screener: your rules against a metrics file, pass/fail per rule, ranked shortlist.

Metrics come from /trader-analyst (trader/metrics.json) or any CSV with a `symbol`
column, e.g. a Screener.in or Tickertape export. Rules are a JSON list:

  {"rules": [
     {"field": "revenue_yoy", "op": ">=", "value": 10},
     {"field": "net_margin", "op": ">", "value": 8},
     {"field": "pe", "op": "<=", "value": 40},
     {"field": "promoter_pledge_pct", "op": "<=", "value": 5, "missing": "pass"},
     {"field": "sector", "op": "not in", "value": ["Tobacco"]}
   ],
   "rank": [{"field": "earnings_yield", "weight": 1}, {"field": "revenue_yoy", "weight": 1}],
   "top": 10}

  python3 screen.py                                  # trader/metrics.json + trader/rules.json
  python3 screen.py export.csv --rules rules.json --write   # shortlist -> trader/targets.json (equal weight)
"""

import argparse
import csv
import io
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402

OPS = {
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b, "not in": lambda a, b: a not in b,
    "between": lambda a, b: b[0] <= a <= b[1],
}


def norm_key(k):
    k = k.strip().lower().replace("%", " pct").replace("₹", "")
    return re.sub(r"[^a-z0-9]+", "_", k).strip("_")


def load_metrics(src):
    if src.lower().endswith(".csv"):
        with open(src, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        out = {}
        for r in rows:
            rec = {norm_key(k): _val(v) for k, v in r.items() if k}
            sym = rec.get("symbol") or rec.get("nse_code") or rec.get("ticker") or rec.get("name")
            if sym:
                rec["symbol"] = str(sym).upper()
                out[rec["symbol"]] = rec
        return out
    data = T.load_json(src, {}) or {}
    return data.get("companies", data)


def _val(v):
    n = T.num(v)
    return n if n is not None else (v.strip() if isinstance(v, str) else v)


def evaluate(company, rules):
    results = []
    for r in rules:
        f, op, want = r["field"], r.get("op", ">="), r.get("value")
        have = company.get(f)
        if have is None or have == "":
            ok = r.get("missing", "fail") == "pass"
            results.append({"field": f, "ok": ok, "have": None, "why": "no data (%s)" % ("passes" if ok else "fails")})
            continue
        if op not in OPS:
            raise SystemExit("unknown op %r in rule for %s" % (op, f))
        a, b = have, want
        if isinstance(a, str) and op in ("in", "not in"):
            a = a.lower()
            b = [str(x).lower() for x in b]
        try:
            ok = OPS[op](a, b)
        except TypeError:
            ok = False
        margin = None
        if isinstance(have, (int, float)) and isinstance(want, (int, float)):
            margin = have - want
        results.append({"field": f, "ok": ok, "have": have, "margin": margin,
                        "why": "%s (rule: %s %s)" % (_fmt(have), op, _fmt(want))})
    return results


def _fmt(v):
    if isinstance(v, float):
        return "%.2f" % v
    if isinstance(v, list):
        return "[" + ", ".join(map(str, v)) + "]"
    return str(v)


def rank(passed, spec):
    if not spec or not passed:
        return passed
    scores = {c["symbol"]: 0.0 for c in passed}
    for s in spec:
        f, w = s["field"], float(s.get("weight", 1))
        vals = sorted([c[f] for c in passed if isinstance(c.get(f), (int, float))], reverse=not s.get("ascending"))
        for c in passed:
            v = c.get(f)
            if isinstance(v, (int, float)) and len(vals) > 1:
                scores[c["symbol"]] += w * (1 - vals.index(v) / (len(vals) - 1))
    for c in passed:
        c["_score"] = round(scores[c["symbol"]], 3)
    return sorted(passed, key=lambda c: -c["_score"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("metrics", nargs="?", default=None)
    ap.add_argument("--rules", default=None)
    ap.add_argument("--top", type=int)
    ap.add_argument("--write", action="store_true", help="shortlist -> trader/targets.json, equal weights")
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args(argv)
    src = a.metrics or T.path("metrics.json")
    if not os.path.exists(src):
        T.die("No metrics at %s. Run /trader-analyst SYMBOLS --write, or pass a CSV." % src)
    spec = T.load_json(a.rules or T.path("rules.json"))
    if not spec:
        T.die("No rules. Copy trader-screener/rules.example.json to trader/rules.json and edit it.")
    rules = spec.get("rules", spec) if isinstance(spec, dict) else spec
    companies = load_metrics(src)
    passed, failed = [], []
    for sym, c in sorted(companies.items()):
        c = dict(c, symbol=c.get("symbol", sym))
        res = evaluate(c, rules)
        (passed if all(r["ok"] for r in res) else failed).append((c, res))
    ranked = rank([c for c, _ in passed], spec.get("rank") if isinstance(spec, dict) else None)
    top = a.top or (spec.get("top") if isinstance(spec, dict) else None)
    if top:
        ranked = ranked[:top]
    print("%d of %d companies pass %d rules" % (len(passed), len(companies), len(rules)))
    if ranked:
        fields = [r["field"] for r in rules if isinstance(ranked[0].get(r["field"]), (int, float))][:6]
        rows = [[i, c["symbol"]] + [_fmt(c.get(f)) if c.get(f) is not None else "-" for f in fields] +
                [c.get("_score", "")] for i, c in enumerate(ranked, 1)]
        print(T.table(rows, ["#", "symbol"] + fields + ["score"]))
    for c, res in failed:
        bad = [r for r in res if not r["ok"]]
        print("  FAIL %-12s %s" % (c["symbol"], "; ".join("%s: %s" % (r["field"], r["why"]) for r in bad)))
        if a.verbose:
            for r in res:
                if r["ok"]:
                    print("       ok   %s: %s" % (r["field"], r["why"]))
    if a.write and ranked:
        w = round(100.0 / len(ranked), 4)
        T.save_json(T.path("targets.json"), {"source": "trader-screener", "as_of": T.now_ist().date().isoformat(),
                                             "generated": T.now_ist().isoformat(timespec="seconds"),
                                             "targets": [{"symbol": c["symbol"], "weight": w} for c in ranked]})
        print("-> %s: %d equal-weight targets. Next: /trader-budget." % (T.path("targets.json"), len(ranked)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
