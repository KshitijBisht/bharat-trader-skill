"""tax and rebalance."""

import unittest

from _load import TraderDir, load

import inr as T

lots = load("trader-tax", "lots")
rebalance = load("trader-rebalance", "rebalance")
t = dict(lots.TAX)


class Tax(unittest.TestCase):
    def test_long_term_is_more_than_12_months(self):
        self.assertFalse(lots.is_long("2025-11-05", "2026-11-05", t))
        self.assertTrue(lots.is_long("2025-11-05", "2026-11-06", t))
        self.assertTrue(lots.is_long("2024-02-29", "2025-03-01", t))

    def test_tax_with_exemption_and_setoff(self):
        x = lots.tax_on(50000, 200000, t)
        self.assertEqual(x["taxable_lt"], 75000)
        self.assertAlmostEqual(x["tax"], (50000 * 0.20 + 75000 * 0.125) * 1.04, places=2)
        x = lots.tax_on(-30000, 100000, t)                 # ST loss eats LT gain
        self.assertEqual(x["lt_net"], 70000)
        self.assertEqual(x["tax"], 0)
        x = lots.tax_on(40000, -10000, t)                  # LT loss cannot touch ST gain
        self.assertEqual(x["carry_forward"]["lt_loss"], 10000)
        self.assertAlmostEqual(x["tax"], 40000 * 0.20 * 1.04, places=2)

    def test_grandfathering(self):
        # bought 2016 at 1500/share (cost 4500 for 3), FMV 31 Jan 2018 = 1100
        self.assertEqual(lots.grandfathered_cost(4500, 3, "2016-05-10", 2000, 1100, t), 4500)
        self.assertEqual(lots.grandfathered_cost(3000, 3, "2016-05-10", 2000, 1100, t), 3300)
        self.assertEqual(lots.grandfathered_cost(3000, 3, "2016-05-10", 1050, 1100, t), 3150)
        self.assertEqual(lots.grandfathered_cost(3000, 3, "2019-05-10", 2000, 1100, t), 3000)

    def test_lot_view(self):
        with TraderDir():
            v = lots.lot_view({"symbol": "ITC", "qty": 10, "price": 300, "cost": 3010, "date": "2026-01-10"}, 350,
                              "2026-11-05", t)
            self.assertEqual(v["term"], "ST")
            self.assertEqual(v["long_term_from"], "2027-01-11")
            self.assertAlmostEqual(v["gain"], 3500 - T.charges("SELL", 3500)["total"] - 3010, places=2)


class Rebalance(unittest.TestCase):
    cfg = dict(T.DEFAULTS, max_position_pct=50)

    def test_inside_band_no_trades(self):
        p = {"cash": 500, "positions": {"A": {"qty": 50}, "B": {"qty": 48}}}
        r = rebalance.plan(p, [{"symbol": "A", "weight": 50}, {"symbol": "B", "weight": 50}],
                           {"A": 100.0, "B": 100.0}, self.cfg)
        self.assertEqual([x for x in r["trades"] if not x["skip"]], [])

    def test_drift_sells_first_and_exits(self):
        p = {"cash": 1000, "positions": {"A": {"qty": 150}, "B": {"qty": 30}, "OLD": {"qty": 20}}}
        r = rebalance.plan(p, [{"symbol": "A", "weight": 50}, {"symbol": "B", "weight": 50}],
                           {"A": 100.0, "B": 100.0, "OLD": 100.0}, self.cfg)
        live = [x for x in r["trades"] if not x["skip"]]
        self.assertEqual([x["side"] for x in live][:2], ["SELL", "SELL"])
        old = [x for x in live if x["symbol"] == "OLD"][0]
        self.assertEqual(old["qty"], 20)
        b = [x for x in live if x["symbol"] == "B"][0]
        self.assertEqual(b["side"], "BUY")

    def test_charges_too_high_skipped(self):
        p = {"cash": 300, "positions": {"A": {"qty": 9}}}
        r = rebalance.plan(p, [{"symbol": "A", "weight": 50}, {"symbol": "B", "weight": 50}],
                           {"A": 100.0, "B": 100.0}, dict(self.cfg, min_order_inr=50))
        b = [x for x in r["trades"] if x["symbol"] == "B"][0]
        self.assertIn("charges", b["skip"])


if __name__ == "__main__":
    unittest.main()
