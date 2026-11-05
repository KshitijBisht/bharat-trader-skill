#!/usr/bin/env python3
"""Order Executor: tickets, your yes, then a paper fill or (only if you set it up) Groww.

Three gates for every order, every time:
  1. trader-risk passed this exact order today (fingerprint match in trader/risk.json)
  2. you typed an explicit yes for this one order (recorded word for word)
  3. your agent's own permission prompt for the command that places it

  python3 ticket.py show                          # every ticket, READY or not
  python3 ticket.py approve --index 1 --reply "yes"
  python3 ticket.py place --index 1               # paper fill (default) at the last price
  python3 ticket.py place --index 1 --live        # Groww, only when paper=false and keys are set
  python3 ticket.py result --index 1 --status EXECUTED --broker-id GMK39038RDT490CCVRO
  python3 ticket.py fill --symbol ITC --side BUY --qty 6 --price 409.85
  python3 ticket.py log

Paper is the default. Live needs all of: config "paper": false, `pip install growwapi
pyotp`, GROWW_API_KEY plus GROWW_TOTP_SECRET (TOTP flow) or GROWW_API_SECRET (daily
approval flow) in the environment, and --live on the command line. Keys are read
from the environment only, never from files or the chat.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-common"))
import inr as T  # noqa: E402
import ledger as L  # noqa: E402

YES = {"yes", "y", "yes place it", "yes, place it", "place it", "approve", "approved", "confirm",
       "confirmed", "go ahead", "haan", "haan ji", "ha", "ji haan", "yes go ahead", "yes, go ahead"}
NOT_YES = re.compile(r"\b(no|not|don'?t|wait|stop|cancel|later|maybe|nahi|mat)\b|\?", re.I)


def is_yes(reply):
    r = re.sub(r"\s+", " ", (reply or "").strip().lower()).rstrip(".!")
    if not r or NOT_YES.search(r):
        return False
    return r in YES


def load_all():
    of = T.load_json(T.path("orders.json"), {}) or {}
    risk = T.load_json(T.path("risk.json"), {}) or {}
    log = T.load_json(T.path("broker-log.json"), []) or []
    return of, risk, log


def verdict_for(item, risk):
    if risk.get("date") != T.now_ist().date().isoformat():
        return None
    fp = T.fingerprint(item["order"])
    for v in risk.get("verdicts", []):
        if v["fingerprint"] == fp:
            return v
    return None


def _today(e):
    return str(e.get("at", "")).startswith(T.now_ist().date().isoformat())


def approval_for(item, log):
    """Today's latest reply for this exact order decides: a later 'no' cancels an earlier 'yes'."""
    fp = T.fingerprint(item["order"])
    for e in reversed(log):
        if e.get("fingerprint") == fp and e.get("event") in ("approved", "declined") and _today(e):
            return e if e["event"] == "approved" else None
    return None


def placed_fingerprints(log):
    return {e.get("fingerprint") for e in log if e.get("event") == "placed" and _today(e)}


def already_placed(item, log):
    return T.fingerprint(item["order"]) in placed_fingerprints(log)


def state(item, risk, log):
    v = verdict_for(item, risk)
    if already_placed(item, log):
        return "PLACED", v
    if v is None:
        return "NEEDS RISK CHECK", v
    if v["verdict"] != "PASS":
        return "BLOCKED", v
    if not approval_for(item, log):
        return "NEEDS YOUR YES", v
    waiting = [fp for fp in v.get("depends_on", []) if fp not in placed_fingerprints(log)]
    if waiting:
        return "WAITING FOR SELLS", v
    return "READY", v


def ticket_text(item, cfg):
    o = item["order"]
    side = {"BUY": "Buy", "SELL": "Sell"}.get(o["transaction_type"], "??? %r" % o["transaction_type"])
    price = "market" if o["order_type"] == "MARKET" else "limit %s" % T.inr(o["price"])
    est = item.get("est_value")
    return ("%s %d %s on %s, %s, %s, delivery (%s), est. %s + %s charges%s"
            % (side, o["quantity"], o["trading_symbol"], o["exchange"], price, o["validity"].lower(),
               o["product"], T.inr(est or 0), T.inr(item.get("est_charges") or 0),
               " [PAPER]" if cfg.get("paper", True) else " [LIVE]"))


def find(of, index):
    for item in of.get("orders", []):
        if item.get("index") == index:
            return item
    T.die("No order #%s in trader/orders.json." % index)


def log_event(log, item, event, **extra):
    e = {"at": T.now_ist().isoformat(timespec="seconds"), "event": event, "index": item.get("index"),
         "fingerprint": T.fingerprint(item["order"]), "order": item["order"]}
    e.update(extra)
    log.append(e)
    T.save_json(T.path("broker-log.json"), log)
    return e


def cmd_show(a, cfg):
    of, risk, log = load_all()
    if not of.get("orders"):
        T.die("No orders. Run /trader-budget (or rebalance / tax) and /trader-risk first.")
    for item in of["orders"]:
        st, v = state(item, risk, log)
        print("#%s  %-16s %s" % (item["index"], st, ticket_text(item, cfg)))
        if st == "BLOCKED":
            print("     blocked: %s" % "; ".join(v["reasons"]))
        if st == "WAITING FOR SELLS" or (v and v.get("depends_on") and st == "NEEDS YOUR YES"):
            print("     place the sell orders above first: this buy is paid for by them")
        if a.json:
            o = dict(item["order"], order_reference_id=T.reference_id(item["order"]))
            print("     place_order(%s)" % ", ".join("%s=%r" % (k, o[k]) for k in o))
    print("Mode: %s. Market: %s." % ("PAPER" if cfg.get("paper", True) else "LIVE (Groww)",
                                     T.market_state()["state"]))
    return 0


def cmd_approve(a, cfg):
    of, risk, log = load_all()
    item = find(of, a.index)
    st, v = state(item, risk, log)
    if st in ("NEEDS RISK CHECK", "BLOCKED", "PLACED"):
        T.die("#%d is %s. Nothing approved." % (a.index, st))
    if not is_yes(a.reply):
        log_event(log, item, "declined", reply=a.reply)
        T.die("Reply %r is not an explicit yes. Nothing approved. Ask again with the exact ticket." % a.reply, 1)
    log_event(log, item, "approved", reply=a.reply, ticket=ticket_text(item, cfg))
    print("Approved #%d (%s): %s" % (a.index, a.reply, ticket_text(item, cfg)))
    return 0


def groww_client():
    try:
        from growwapi import GrowwAPI
    except ImportError:
        T.die("Live mode needs the Groww SDK: pip install growwapi pyotp")
    key = os.environ.get("GROWW_API_KEY")
    totp_secret = os.environ.get("GROWW_TOTP_SECRET")
    secret = os.environ.get("GROWW_API_SECRET")
    if not key or not (totp_secret or secret):
        T.die("Set GROWW_API_KEY and GROWW_TOTP_SECRET (or GROWW_API_SECRET) in your environment. "
              "Never paste them into the chat.")
    if totp_secret:
        import pyotp
        token = GrowwAPI.get_access_token(api_key=key, totp=pyotp.TOTP(totp_secret).now())
    else:
        token = GrowwAPI.get_access_token(api_key=key, secret=secret)
    return GrowwAPI(token)


def cmd_place(a, cfg):
    of, risk, log = load_all()
    item = find(of, a.index)
    st, v = state(item, risk, log)
    if st != "READY":
        T.die("#%d is %s, not READY. Nothing placed." % (a.index, st), 1)
    o = item["order"]
    live = a.live and not cfg.get("paper", True)
    if a.live and cfg.get("paper", True):
        T.die('--live given but config has "paper": true. Nothing placed.', 1)
    if not live:
        px = T.prices().get(o["trading_symbol"]) or T.num(item.get("est_price"))
        if not px:
            T.die("No price for %s. Run trader-alerts quote." % o["trading_symbol"])
        p = L.load()
        date = T.now_ist().date().isoformat()
        try:
            ch = L.apply_fill(p, o["trading_symbol"], o["transaction_type"], o["quantity"], px, date,
                              o["exchange"], cfg)
        except ValueError as exc:
            T.die(str(exc))
        L.save(p)
        log_event(log, item, "placed", mode="paper", fill_price=px, charges=ch)
        print("PAPER fill #%d: %s %d %s @ %s, charges %s. Cash now %s."
              % (a.index, o["transaction_type"], o["quantity"], o["trading_symbol"], T.inr(px), T.inr(ch),
                 T.inr(p["cash"])))
        return 0
    g = groww_client()
    ref = T.reference_id(o)
    resp = g.place_order(order_reference_id=ref, **o)
    log_event(log, item, "placed", mode="live", broker="groww", response=resp, order_reference_id=ref)
    print("Sent to Groww #%d: %s -> %s" % (a.index, ticket_text(item, cfg), resp))
    print("Check its status, then record the fill: ticket.py fill --symbol %s --side %s --qty N --price P"
          % (o["trading_symbol"], o["transaction_type"]))
    return 0


def cmd_result(a, cfg):
    of, risk, log = load_all()
    item = find(of, a.index)
    log_event(log, item, "result", status=a.status, broker_id=a.broker_id, note=a.note)
    print("Recorded #%d: %s %s" % (a.index, a.status, a.broker_id or ""))
    return 0


def cmd_fill(a, cfg):
    p = L.load()
    date = a.date or T.now_ist().date().isoformat()
    try:
        ch = L.apply_fill(p, a.symbol, a.side, a.qty, a.price, date, a.exchange, cfg, a.charges)
    except ValueError as exc:
        T.die(str(exc))
    L.save(p)
    log = T.load_json(T.path("broker-log.json"), []) or []
    log.append({"at": T.now_ist().isoformat(timespec="seconds"), "event": "fill", "symbol": a.symbol.upper(),
                "side": a.side.upper(), "qty": a.qty, "price": a.price, "charges": ch, "date": date})
    T.save_json(T.path("broker-log.json"), log)
    print("Booked %s %d %s @ %s (charges %s). Cash %s." % (a.side.upper(), a.qty, a.symbol.upper(),
                                                          T.inr(a.price), T.inr(ch), T.inr(p["cash"])))
    return 0


def cmd_log(a, cfg):
    log = T.load_json(T.path("broker-log.json"), []) or []
    for e in log[-a.last:]:
        extra = e.get("reply") or e.get("mode") or e.get("status") or ""
        sym = (e.get("order") or {}).get("trading_symbol") or e.get("symbol", "")
        print("%s  %-9s #%-3s %-12s %s" % (e["at"], e["event"], e.get("index") or "-", sym, extra))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--json", action="store_true", help="also print the exact place_order arguments")
    s = sub.add_parser("approve")
    s.add_argument("--index", type=int, required=True)
    s.add_argument("--reply", required=True, help="the user's reply, word for word")
    s = sub.add_parser("place")
    s.add_argument("--index", type=int, required=True)
    s.add_argument("--live", action="store_true")
    s = sub.add_parser("result")
    s.add_argument("--index", type=int, required=True)
    s.add_argument("--status", required=True)
    s.add_argument("--broker-id")
    s.add_argument("--note")
    s = sub.add_parser("fill")
    s.add_argument("--symbol", required=True)
    s.add_argument("--side", required=True, choices=["BUY", "SELL", "buy", "sell"])
    s.add_argument("--qty", type=int, required=True)
    s.add_argument("--price", type=float, required=True)
    s.add_argument("--date")
    s.add_argument("--exchange", default="NSE")
    s.add_argument("--charges", type=float, help="actual charges from the contract note")
    s = sub.add_parser("log")
    s.add_argument("--last", type=int, default=30)
    a = ap.parse_args(argv)
    cfg = T.config()
    return {"show": cmd_show, "approve": cmd_approve, "place": cmd_place, "result": cmd_result,
            "fill": cmd_fill, "log": cmd_log}[a.cmd](a, cfg)


if __name__ == "__main__":
    sys.exit(main())
