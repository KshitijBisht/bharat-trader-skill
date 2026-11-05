import datetime as dt
import unittest

from _load import TraderDir, read

import inr as T
import xlsx


class Charges(unittest.TestCase):
    def test_thousand_rupee_round_trip(self):
        b = T.charges("BUY", 1000)
        s = T.charges("SELL", 1000)
        self.assertEqual(b["brokerage"], 5.0)        # minimum Rs 5
        self.assertEqual(b["stt"], 1.0)
        self.assertEqual(b["stamp"], 0.15)
        self.assertEqual(b["dp"], 0.0)
        self.assertEqual(s["dp"], 20.0)
        self.assertEqual(s["stamp"], 0.0)
        self.assertAlmostEqual(b["total"], 7.09, places=2)
        self.assertAlmostEqual(s["total"], 30.54, places=2)
        self.assertAlmostEqual(T.round_trip_pct(1000), 3.763, places=3)

    def test_brokerage_cap_and_percent(self):
        self.assertEqual(T.charges("BUY", 100000)["brokerage"], 20.0)    # capped at Rs 20
        self.assertEqual(T.charges("BUY", 8000)["brokerage"], 8.0)       # 0.1%

    def test_no_dp_under_100_and_bse_rate(self):
        self.assertEqual(T.charges("SELL", 99)["dp"], 0.0)
        self.assertGreater(T.charges("BUY", 10000, "BSE")["exchange"], T.charges("BUY", 10000, "NSE")["exchange"])

    def test_override_from_config(self):
        cfg = {"charges": {"brokerage_pct": 0, "brokerage_min": 0, "brokerage_max": 0}}
        self.assertEqual(T.charges("BUY", 1000, cfg=cfg)["brokerage"], 0.0)


class Money(unittest.TestCase):
    def test_indian_grouping(self):
        self.assertEqual(T.inr(1234567.891), "₹12,34,567.89")
        self.assertEqual(T.inr(999), "₹999.00")
        self.assertEqual(T.inr(-125000, 0), "-₹1,25,000")

    def test_rounding_up_to_the_rupee(self):
        self.assertEqual(T.inr(1.999), "₹2.00")
        self.assertEqual(T.inr(99.999), "₹100.00")
        self.assertEqual(T.inr(409.995), "₹410.00")
        self.assertEqual(T.inr(-0.004), "₹0.00")

    def test_stt_halves_round_up(self):
        self.assertEqual(T.charges("BUY", 500)["stt"], 1.0)
        self.assertEqual(T.charges("BUY", 2500)["stt"], 3.0)

    def test_num(self):
        self.assertEqual(T.num("1,23,456.70"), 123456.7)
        self.assertIsNone(T.num("-"))
        self.assertEqual(T.num(None, 0), 0)


class Calendar(unittest.TestCase):
    def test_holidays_and_weekends(self):
        with TraderDir():
            self.assertFalse(T.is_trading_day(dt.date(2026, 11, 10)))   # Diwali Balipratipada
            self.assertFalse(T.is_trading_day(dt.date(2026, 11, 7)))    # Saturday
            self.assertTrue(T.is_trading_day(dt.date(2026, 11, 5)))
            self.assertEqual(T.next_trading_day(dt.date(2026, 11, 9)), dt.date(2026, 11, 11))

    def test_market_state(self):
        with TraderDir():
            at = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=T.IST)
            self.assertEqual(T.market_state(at("2026-11-05T09:05"))["state"], "pre-open")
            self.assertEqual(T.market_state(at("2026-11-05T09:15"))["state"], "open")
            self.assertEqual(T.market_state(at("2026-11-05T15:45"))["state"], "post-close")
            st = T.market_state(at("2026-11-10T11:00"))
            self.assertEqual(st["state"], "holiday")
            self.assertTrue(st["next_open"].startswith("2026-11-11"))

    def test_builtin_holidays_match_nse_file(self):
        import json
        cm = json.loads(read("trader-alerts", "nse-holidays-2026.json"))["CM"]
        nse = {T.parse_date(r["tradingDate"]).date().isoformat() for r in cm}
        self.assertEqual(nse, set(T.NSE_HOLIDAYS))

    def test_financial_year(self):
        self.assertEqual(T.financial_year("2026-11-05"), "FY2026-27")
        self.assertEqual(T.financial_year("2027-03-31"), "FY2026-27")
        self.assertEqual(T.financial_year("2027-04-01"), "FY2027-28")


class Orders(unittest.TestCase):
    def test_groww_shape(self):
        o = T.groww_order("itc", 7, "buy")
        self.assertEqual(o, {"trading_symbol": "ITC", "quantity": 7, "price": 0.0, "trigger_price": None,
                             "validity": "DAY", "exchange": "NSE", "segment": "CASH", "product": "CNC",
                             "order_type": "MARKET", "transaction_type": "BUY"})

    def test_fingerprint_and_reference(self):
        a = T.groww_order("ITC", 7, "BUY")
        b = T.groww_order("ITC", 8, "BUY")
        self.assertNotEqual(T.fingerprint(a), T.fingerprint(b))
        ref = T.reference_id(a, "20261105")
        self.assertTrue(8 <= len(ref) <= 20)
        self.assertLessEqual(ref.count("-"), 2)
        self.assertTrue(ref.replace("-", "").isalnum())


class Xlsx(unittest.TestCase):
    def test_reads_amc_sheet(self):
        rows = xlsx.rows(read("trader-copycat", "PPFCF-2026-09-30.xlsx", mode="rb"))
        self.assertIn("Parag Parikh Flexi Cap Fund", rows[0][1])
        hdfc = [r for r in rows if len(r) > 2 and r[2] == "INE040A01034"][0]
        self.assertEqual(hdfc[1], "HDFC Bank Limited")

    def test_rejects_xls(self):
        with self.assertRaises(ValueError):
            xlsx.rows(b"\xd0\xcf\x11\xe0 old xls")


if __name__ == "__main__":
    unittest.main()
