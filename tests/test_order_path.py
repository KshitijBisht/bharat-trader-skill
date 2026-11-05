"""budget -> risk -> broker, offline, including every gate."""

import io
import json
import os
import unittest


def jload(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
from contextlib import redirect_stdout, redirect_stderr

from _load import TraderDir, fixture, load

import inr as T
import ledger as L

size = load("trader-budget", "size")
check = load("trader-risk", "check")
ticket = load("trader-broker", "ticket")

PX = {"HDFCBANK": 736.70, "POWERGRID": 262.05, "ITC": 280.00, "COALINDIA": 399.65, "ICICIBANK": 1424.10}
TARGETS = [{"symbol": "HDFCBANK", "weight": 7.75}, {"symbol": "POWERGRID", "weight": 5.60},
           {"symbol": "ITC", "weight": 5.49}, {"symbol": "COALINDIA", "weight": 5.39},
           {"symbol": "ICICIBANK", "weight": 5.24}]


def quiet(fn, *a):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = fn(*a)
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue() + err.getvalue()


class Budget(unittest.TestCase):
    def test_cap_weights_redistributes(self):
        w = size.cap_weights({"A": 0.6, "B": 0.3, "C": 0.1}, 0.4)
        self.assertAlmostEqual(w["A"], 0.4)
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w["B"], 0.4)              # B goes over the cap after A's share-out
        self.assertAlmostEqual(w["C"], 0.2)

    def test_ten_thousand_plan(self):
        p = size.plan(TARGETS, PX, dict(T.DEFAULTS, budget=10000))
        got = {o["symbol"]: o["qty"] for o in p["orders"]}
        self.assertEqual(got, {"HDFCBANK": 3, "POWERGRID": 7, "ITC": 7, "COALINDIA": 5, "ICICIBANK": 1})
        self.assertAlmostEqual(p["spent"], 9467.04, places=2)
        self.assertGreaterEqual(p["cash_left"], p["buffer"])
        for o in p["orders"]:
            self.assertLessEqual(o["est_value"], 10000 * 0.25 + 1e-6)
            self.assertIsInstance(o["qty"], int)

    def test_thousand_rupees_fits_nothing(self):
        p = size.plan(TARGETS, PX, dict(T.DEFAULTS, budget=1000))
        self.assertEqual(p["orders"], [])
        self.assertEqual(len(p["dropped"]), 5)

    def test_missing_price_and_blocked(self):
        p = size.plan(TARGETS + [{"symbol": "NOPRICE", "weight": 5}], PX,
                      dict(T.DEFAULTS, budget=10000, blocked=["ITC"]))
        self.assertIn("NOPRICE", p["missing"])
        self.assertNotIn("ITC", [o["symbol"] for o in p["orders"]])

    def test_lots(self):
        p = size.plan([{"symbol": "X", "weight": 1}], {"X": 100.0}, dict(T.DEFAULTS, budget=1000, max_position_pct=100),
                      lots={"X": 4})
        self.assertEqual(p["orders"][0]["qty"] % 4, 0)


class Risk(unittest.TestCase):
    def cfg(self, **kw):
        return dict(T.DEFAULTS, budget=10000, **kw)

    def item(self, sym, qty, side="BUY", index=1, **o):
        order = T.groww_order(sym, qty, side)
        order.update(o)
        return {"index": index, "order": order}

    def verdict(self, items, cfg=None, portfolio=None, px=None, **kw):
        res = check.check(items, cfg or self.cfg(), portfolio or {"cash": 10000}, px or PX, **kw)
        return res["verdicts"]

    def test_pass(self):
        v = self.verdict([self.item("ITC", 7)])
        self.assertEqual(v[0]["verdict"], "PASS", v[0]["reasons"])

    def test_each_block(self):
        cases = [
            (self.item("ITC", 7), self.cfg(blocked=["ITC"]), "blocked list"),
            (self.item("ITC", 20), self.cfg(), "max_order_inr"),
            (self.item("ITC", 1), self.cfg(), "round trip"),
            (self.item("HDFCBANK", 4), self.cfg(), "cap"),
            (self.item("ITC", 7, product="MIS"), self.cfg(), "intraday"),
            (self.item("ITC", 7, segment="FNO"), self.cfg(), "F&O"),
            (self.item("ITC", 7, product="MTF"), self.cfg(), "MTF"),
            (self.item("ITC", 7, "SELL"), self.cfg(), "short selling"),
            (self.item("ITC", 7, order_type="LIMIT", price=0), self.cfg(), "needs a price"),
            (self.item("ITC", 7, transaction_type="buy"), self.cfg(), "exactly BUY or SELL"),
            (self.item("ITC", 7, order_type="limit"), self.cfg(), "exactly MARKET"),
        ]
        frac = self.item("ITC", 7)
        frac["order"]["quantity"] = 2.5
        cases.append((frac, self.cfg(), "whole number"))
        for item, cfg, needle in cases:
            v = self.verdict([item], cfg)[0]
            self.assertEqual(v["verdict"], "BLOCK", needle)
            self.assertTrue(any(needle in r for r in v["reasons"]), (needle, v["reasons"]))

    def test_buffer(self):
        v = self.verdict([self.item("ITC", 7)], portfolio={"cash": 2000})
        self.assertTrue(any("buffer" in r for r in v[0]["reasons"]))

    def test_surveillance_t2t_sme(self):
        v = self.verdict([self.item("ITC", 7)], surv={"ITC": "LTASM - Stage I"})
        self.assertTrue(any("surveillance" in r for r in v[0]["reasons"]))
        v = self.verdict([self.item("ITC", 7)], series={"ITC": "BE"})
        self.assertTrue(any("trade-to-trade" in r for r in v[0]["reasons"]))
        v = self.verdict([self.item("ITC", 7)], series={"ITC": "SM"})
        self.assertTrue(any("SME" in r for r in v[0]["reasons"]))

    def test_parse_real_surveillance_lists(self):
        asm = jload(fixture("trader-risk", "nse-asm.json"))
        gsm = jload(fixture("trader-risk", "nse-gsm.json"))
        s = check.parse_surveillance(asm, gsm)
        self.assertIn("A2ZINFRA", s)
        self.assertTrue(s["AGSTRA"].startswith("GSM"))

    def test_duplicates_and_daily_limit(self):
        v = self.verdict([self.item("ITC", 7, index=1), self.item("ITC", 7, index=2)])
        self.assertEqual([x["verdict"] for x in v], ["PASS", "BLOCK"])
        v = self.verdict([self.item("ITC", 7)], placed_today=10)
        self.assertTrue(any("max_orders_per_day" in r for r in v[0]["reasons"]))

    def test_sells_free_cash_first(self):
        port = {"cash": 600, "positions": {"POWERGRID": {"qty": 20, "avg_price": 250}}}
        items = [self.item("ITC", 7, index=1), self.item("POWERGRID", 10, "SELL", index=2)]
        v = self.verdict(items, self.cfg(max_position_pct=40), portfolio=port)
        self.assertEqual([x["verdict"] for x in v], ["PASS", "PASS"], [x["reasons"] for x in v])


class Broker(unittest.TestCase):
    def setup_orders(self, d):
        T.save_json(d.path("config.json"), {"budget": 10000})
        T.save_json(d.path("targets.json"), {"targets": TARGETS})
        T.save_json(d.path("prices.json"), {"quotes": {k: {"price": v} for k, v in PX.items()}})
        rc, _ = quiet(size.main, ["--write"])
        self.assertEqual(rc, 0)

    def test_yes_words(self):
        for y in ("yes", "Yes.", "  YES  ", "yes, place it", "haan", "confirm"):
            self.assertTrue(ticket.is_yes(y), y)
        for n in ("", "no", "maybe", "yes?", "ok I guess", "not yes", "yes but wait", "sure", "yes to all"):
            self.assertFalse(ticket.is_yes(n), n)

    def test_three_gates_and_paper_fill(self):
        with TraderDir() as d:
            self.setup_orders(d)
            rc, out = quiet(ticket.main, ["place", "--index", "3"])
            self.assertNotEqual(rc, 0)
            self.assertIn("NEEDS RISK CHECK", out)
            rc, out = quiet(ticket.main, ["approve", "--index", "3", "--reply", "yes"])
            self.assertNotEqual(rc, 0)                       # no risk check yet: approval refused

            quiet(check.main, [])
            rc, out = quiet(ticket.main, ["approve", "--index", "3", "--reply", "maybe?"])
            self.assertEqual(rc, 1)
            rc, out = quiet(ticket.main, ["place", "--index", "3"])
            self.assertIn("NEEDS YOUR YES", out)

            rc, out = quiet(ticket.main, ["approve", "--index", "3", "--reply", "yes"])
            self.assertEqual(rc, 0, out)
            rc, out = quiet(ticket.main, ["place", "--index", "3", "--live"])
            self.assertIn("paper", out)                      # live refused while paper=true
            rc, out = quiet(ticket.main, ["place", "--index", "3"])
            self.assertEqual(rc, 0, out)
            self.assertIn("PAPER fill #3", out)
            p = L.load()
            self.assertEqual(p["positions"]["ITC"]["qty"], 7)
            self.assertAlmostEqual(p["cash"], 10000 - 1960 - 8.26, places=2)

            rc, out = quiet(ticket.main, ["place", "--index", "3"])
            self.assertIn("PLACED", out)                     # never twice
            rc, out = quiet(ticket.main, ["approve", "--index", "5", "--reply", "yes"])
            self.assertIn("BLOCKED", out)                    # ICICIBANK: charges

            log = jload(d.path("broker-log.json"))
            self.assertEqual([e["event"] for e in log], ["declined", "approved", "placed"])
            self.assertEqual(log[0]["reply"], "maybe?")

    def test_later_no_cancels_yes(self):
        with TraderDir() as d:
            self.setup_orders(d)
            quiet(check.main, [])
            quiet(ticket.main, ["approve", "--index", "3", "--reply", "yes"])
            quiet(ticket.main, ["approve", "--index", "3", "--reply", "no, wait"])
            rc, out = quiet(ticket.main, ["place", "--index", "3"])
            self.assertNotEqual(rc, 0)
            self.assertIn("NEEDS YOUR YES", out)

    def test_same_order_tomorrow_is_not_placed(self):
        with TraderDir() as d:
            self.setup_orders(d)
            quiet(check.main, [])
            quiet(ticket.main, ["approve", "--index", "3", "--reply", "yes"])
            quiet(ticket.main, ["place", "--index", "3"])
            os.environ["TRADER_NOW"] = "2026-11-06T10:00"
            quiet(check.main, [])
            rc, out = quiet(ticket.main, ["show"])
            self.assertNotIn("#3  PLACED", out)          # judged afresh (here: blocked by the cap)
            self.assertIn("#3  BLOCKED", out)

    def test_buy_paid_by_sell_waits_for_the_sell(self):
        with TraderDir() as d:
            T.save_json(d.path("config.json"), {"budget": 3000, "max_position_pct": 60, "max_charges_pct": 10})
            T.save_json(d.path("portfolio.json"), {"cash": 600, "lots": [
                {"symbol": "POWERGRID", "qty": 8, "price": 250, "cost": 2000, "date": "2026-01-02"}]})
            T.save_json(d.path("prices.json"), {"quotes": {"POWERGRID": {"price": 262.05}, "ITC": {"price": 280.0}}})
            orders = []
            for i, (sym, q, side) in enumerate([("ITC", 5, "BUY"), ("POWERGRID", 8, "SELL")], 1):
                o = T.groww_order(sym, q, side)
                orders.append({"index": i, "order": o, "est_price": 280.0 if sym == "ITC" else 262.05})
            T.save_json(d.path("orders.json"), {"orders": orders})
            quiet(check.main, [])
            risk = jload(d.path("risk.json"))
            buy = [v for v in risk["verdicts"] if v["side"] == "BUY"][0]
            self.assertEqual(buy["verdict"], "PASS", buy["reasons"])
            self.assertEqual(len(buy["depends_on"]), 1)
            quiet(ticket.main, ["approve", "--index", "1", "--reply", "yes"])
            rc, out = quiet(ticket.main, ["place", "--index", "1"])
            self.assertIn("WAITING FOR SELLS", out)
            quiet(ticket.main, ["approve", "--index", "2", "--reply", "yes"])
            quiet(ticket.main, ["place", "--index", "2"])
            rc, out = quiet(ticket.main, ["place", "--index", "1"])
            self.assertEqual(rc, 0, out)

    def test_risk_verdict_expires_next_day(self):
        with TraderDir() as d:
            self.setup_orders(d)
            quiet(check.main, [])
            os.environ["TRADER_NOW"] = "2026-11-06T10:00"
            rc, out = quiet(ticket.main, ["show"])
            self.assertIn("NEEDS RISK CHECK", out)

    def test_edited_order_needs_new_check(self):
        with TraderDir() as d:
            self.setup_orders(d)
            quiet(check.main, [])
            of = jload(d.path("orders.json"))
            of["orders"][2]["order"]["quantity"] = 70
            T.save_json(d.path("orders.json"), of)
            rc, out = quiet(ticket.main, ["approve", "--index", "3", "--reply", "yes"])
            self.assertIn("NEEDS RISK CHECK", out)


class Ledger(unittest.TestCase):
    def test_fifo_and_realized(self):
        with TraderDir():
            p = {"cash": 10000, "positions": {}, "lots": [], "realized": []}
            L.apply_fill(p, "ITC", "BUY", 10, 300, "2025-01-10", charges=10)
            L.apply_fill(p, "ITC", "BUY", 10, 350, "2026-01-10", charges=10)
            L.apply_fill(p, "ITC", "SELL", 15, 400, "2026-11-05", charges=20)
            self.assertEqual(p["positions"]["ITC"]["qty"], 5)
            self.assertEqual([r["qty"] for r in p["realized"]], [10, 5])
            self.assertEqual(p["realized"][0]["buy_date"], "2025-01-10")
            self.assertAlmostEqual(sum(r["gain"] for r in p["realized"]), 6000 - 20 - 3010 - 1755, places=1)
            with self.assertRaises(ValueError):
                L.apply_fill(p, "ITC", "SELL", 6, 400, "2026-11-05")


if __name__ == "__main__":
    unittest.main()
