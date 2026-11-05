"""copycat, insider, news, analyst, screener, alerts parsers on real NSE / AMC files."""

import datetime as dt
import io
import json
import os
import unittest


def jload(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
from contextlib import redirect_stdout

from _load import TraderDir, fixture, load, read

import inr as T

copycat = load("trader-copycat", "copycat")
insider = load("trader-insider", "insider")
news = load("trader-news", "news")
facts = load("trader-analyst", "facts")
screen = load("trader-screener", "screen")
alerts = load("trader-alerts", "alerts")


class Copycat(unittest.TestCase):
    def test_fund_parse(self):
        f = copycat.parse_fund(read("trader-copycat", "PPFCF-2026-09-30.xlsx", mode="rb"))
        self.assertEqual(f["fund"], "Parag Parikh Flexi Cap Fund")
        self.assertEqual(f["as_of"], "2026-09-30")
        self.assertEqual(len(f["holdings"]), 33)
        top = f["holdings"][0]
        self.assertEqual((top["isin"], top["pct_nav"]), ("INE040A01034", 7.75))
        self.assertAlmostEqual(sum(h["pct_nav"] for h in f["holdings"]), 72.06, places=1)
        isins = {h["isin"] for h in f["holdings"]}
        self.assertFalse(any(i.startswith("US") for i in isins))         # foreign stocks left out
        self.assertNotIn("INF879O01068", isins)                           # liquid fund units left out

    def test_fund_diff_and_symbols(self):
        eq = T.equity_list(fixture("trader-budget", "EQUITY_L.csv"))
        now = copycat.parse_fund(read("trader-copycat", "PPFCF-2026-09-30.xlsx", mode="rb"))
        before = copycat.parse_fund(read("trader-copycat", "PPFCF-2026-08-31.xlsx", mode="rb"))
        copycat.symbols_for(now["holdings"], eq)
        copycat.symbols_for(before["holdings"], eq)
        self.assertEqual([h["symbol"] for h in now["holdings"][:5]],
                         ["HDFCBANK", "POWERGRID", "ITC", "COALINDIA", "ICICIBANK"])
        d = {(k, (h or b)["symbol"]) for k, h, b in copycat.diff(now["holdings"], before["holdings"])}
        self.assertIn(("ADDED", "DLF"), d)
        self.assertIn(("SOLD", "GESHIP"), d)

    def test_shp_parse(self):
        s = copycat.parse_shp(read("trader-copycat", "SHP-TITAN-2026Q3.xml", mode="rb"))
        self.assertEqual((s["symbol"], s["as_of"]), ("TITAN", "2026-09-30"))
        self.assertEqual(s["total_shares"], 887786160)
        names = {h["name"].upper() for h in s["holders"]}
        self.assertIn("REKHA JHUNJHUNWALA", names)

    def test_investor_stake_sums_aliases(self):
        inv = copycat.find_investor("rekha")
        titan = copycat.investor_stake(copycat.parse_shp(read("trader-copycat", "SHP-TITAN-2026Q3.xml", mode="rb")),
                                       inv["aliases"])
        self.assertEqual(titan["shares"], 37643895 + 9540575)
        self.assertAlmostEqual(titan["pct"], 5.31, places=2)
        metro = copycat.investor_stake(copycat.parse_shp(read("trader-copycat", "SHP-METROBRAND-2026Q3.xml", mode="rb")),
                                       inv["aliases"])
        self.assertEqual(len(metro["names"]), 3)                           # three family trusts
        infy = copycat.investor_stake(copycat.parse_shp(read("trader-copycat", "SHP-INFY-2026Q3.xml", mode="rb")),
                                      inv["aliases"])
        self.assertEqual(infy["shares"], 0)

    def test_alias_match_is_word_based(self):
        self.assertTrue(copycat.matches("REKHA  JHUNJHUNWALA", ["Rekha Jhunjhunwala"]))
        self.assertTrue(copycat.matches("ARYAMAN JHUNJHUNWALA DISCRETIONARY TRUST (TRUSTEE - X)",
                                        ["Aryaman Jhunjhunwala Discretionary Trust"]))
        self.assertFalse(copycat.matches("REKHAJHUNJHUNWALAX LTD", ["Rekha Jhunjhunwala"]))

    def test_ppfas_url(self):
        self.assertEqual(copycat.ppfas_url("PPFCF", "2026-09"),
                         "https://amc.ppfas.com/downloads/portfolio-disclosure/2026/"
                         "PPFCF_PPFAS_Monthly_Portfolio_Report_September_30_2026.xlsx")
        self.assertEqual(copycat.prev_month("2026-01"), "2025-12")

    def test_write_targets(self):
        with TraderDir() as d:
            with redirect_stdout(io.StringIO()):
                copycat.write_targets([{"symbol": "A", "weight": 3}, {"symbol": "B", "weight": 1},
                                       {"symbol": "C", "weight": 0}], "x", "2026-09-30", top=None)
            t = jload(d.path("targets.json"))["targets"]
            self.assertEqual([(x["symbol"], x["weight"]) for x in t], [("A", 75.0), ("B", 25.0)])


class Insider(unittest.TestCase):
    def test_pit(self):
        rows = insider.parse_pit(json.loads(read("trader-insider", "nse-pit-INFY.json")))
        self.assertEqual(len(rows), 20)
        sale = [r for r in rows if r["mode"] == "Market Sale"]
        self.assertEqual(len(sale), 1)
        self.assertEqual(sale[0]["side"], "SELL")
        self.assertTrue(sale[0]["market"])
        self.assertTrue(all(not r["market"] for r in rows if r["mode"] == "ESOP"))
        self.assertTrue(all(r["days_to_disclose"] is not None for r in rows))

    def test_deals(self):
        rows = insider.parse_deals(json.loads(read("trader-insider", "nse-largedeals.json")))
        kinds = {r["kind"] for r in rows}
        self.assertEqual(kinds, {"BULK", "BLOCK"})
        a = [r for r in rows if r["symbol"] == "AJMERA" and r["kind"] == "BLOCK" and r["side"] == "BUY"][0]
        self.assertEqual(a["value"], 2500000 * 141)

    def test_new_alerts_once(self):
        with TraderDir():
            args = ["new", "--pit-file", fixture("trader-insider", "nse-pit-INFY.json"),
                    "--deals-file", fixture("trader-insider", "nse-largedeals.json"), "--all"]
            out1, out2 = io.StringIO(), io.StringIO()
            with redirect_stdout(out1):
                insider.main(args)
            with redirect_stdout(out2):
                insider.main(args)
            self.assertIn("NEW insider trades", out1.getvalue())
            self.assertIn("Nothing new", out2.getvalue())


class News(unittest.TestCase):
    def test_announcements(self):
        items = news.parse_announcements(json.loads(read("trader-news", "nse-announcements-INFY.json")))
        self.assertEqual(len(items), 25)
        self.assertTrue(all(i["when"] is not None for i in items))
        flags = {i["flag"] for i in items}
        self.assertIn("noise", flags)                                  # newspaper publications

    def test_rss(self):
        items = news.parse_rss(read("trader-news", "gnews-INFY.xml"), "INFY")
        self.assertEqual(len(items), 10)
        self.assertTrue(all(i["title"] and i["when"] for i in items))

    def test_classify(self):
        c = news.classify
        self.assertEqual(c("Resignation of Statutory Auditor"), "RED")
        self.assertEqual(c("Creation of pledge on promoter shares"), "RED")
        self.assertEqual(c("Board approves Scheme of Amalgamation"), "DEAL")
        self.assertEqual(c("Copy of Newspaper Publication"), "noise")
        self.assertEqual(c("ITC Just Released Its Second-Quarter Earnings"), "")    # 'ED' inside a word
        self.assertEqual(c("Analysts research note on Titan"), "")                  # 'search' inside a word


class Analyst(unittest.TestCase):
    def test_integrated_filing(self):
        q = facts.parse_result(read("trader-analyst", "INTEGRATED-ITC-30-SEP-2026-consolidated.xml", mode="rb"))
        self.assertEqual((q["symbol"], q["end"], q["basis"]), ("ITC", "2026-09-30", "Consolidated"))
        self.assertEqual(q["revenue"], 305784000000)
        self.assertEqual(q["net_profit"], 42293300000)
        self.assertEqual(q["eps_diluted"], 3.32)
        # EBITDA = PBT + finance + D&A - other income - exceptional
        self.assertAlmostEqual(q["ebitda"], 55976600000 + 382700000 + 4906000000 - 5073600000 + 256600000)

    def test_yoy_and_ttm(self):
        files = sorted(f for f in os.listdir(fixture("trader-analyst")) if f.startswith("INTEGRATED-ITC"))
        qs = [facts.parse_result(read("trader-analyst", f, mode="rb")) for f in files]
        qs, ttm = facts.summarise(qs)
        self.assertEqual(qs[0]["end"], "2026-09-30")
        self.assertAlmostEqual(qs[0]["revenue_yoy"], 43.86, places=2)
        self.assertEqual(ttm["end"], "2026-09-30")
        self.assertAlmostEqual(ttm["eps_diluted"], 3.32 + 3.51 + 4.30 + 3.94, places=2)

    def test_legacy_results(self):
        q = facts.parse_result(read("trader-analyst", "INDAS-INFY-31Dec2024-consolidated.xml", mode="rb"))
        self.assertEqual((q["symbol"], q["end"]), ("INFY", "2024-12-31"))
        self.assertEqual(q["eps_diluted"], 16.39)

    def test_filings_merge_feeds(self):
        integ = json.loads(read("trader-analyst", "nse-integrated-filing-ITC.json"))
        rows = facts.filings("ITC", integrated=integ, legacy=[])
        self.assertEqual(rows[0]["end"], "2026-09-30")
        self.assertTrue(all("INTEGRATED_FILING_INDAS" in r["xbrl"] for r in rows))
        self.assertEqual(len({r["end"] for r in rows}), len(rows))

    def test_metrics_pe(self):
        files = sorted(f for f in os.listdir(fixture("trader-analyst")) if f.startswith("INTEGRATED-ITC"))
        qs, ttm = facts.summarise([facts.parse_result(read("trader-analyst", f, mode="rb")) for f in files])
        m = facts.metrics_row("ITC", qs, ttm, {"ITC": 280.0})
        self.assertAlmostEqual(m["pe"], round(280 / 15.07, 2))
        self.assertGreater(m["market_cap_cr"], 300000)


class Screener(unittest.TestCase):
    def test_rules_and_rank(self):
        cos = {"A": {"symbol": "A", "g": 20, "pe": 10, "sector": "IT"},
               "B": {"symbol": "B", "g": 12, "pe": 30, "sector": "Tobacco"},
               "C": {"symbol": "C", "g": 5, "pe": 8, "sector": "IT"},
               "D": {"symbol": "D", "pe": 9, "sector": "IT"}}
        rules = [{"field": "g", "op": ">=", "value": 10}, {"field": "sector", "op": "not in", "value": ["tobacco"]}]
        res = {k: all(r["ok"] for r in screen.evaluate(c, rules)) for k, c in cos.items()}
        self.assertEqual(res, {"A": True, "B": False, "C": False, "D": False})
        rules[0]["missing"] = "pass"
        self.assertTrue(all(r["ok"] for r in screen.evaluate(cos["D"], rules)))
        ranked = screen.rank([cos["A"], cos["C"]], [{"field": "pe", "ascending": True}])
        self.assertEqual(ranked[0]["symbol"], "C")

    def test_csv_headers(self):
        self.assertEqual(screen.norm_key("Return on capital employed %"), "return_on_capital_employed_pct")
        self.assertEqual(screen.norm_key("Price to Earning"), "price_to_earning")


class Alerts(unittest.TestCase):
    def test_bhav(self):
        q = alerts.parse_bhav(read("trader-alerts", "sec_bhavdata_full_04112026.csv"))
        self.assertEqual(q["ITC"]["price"], 280.0)
        self.assertEqual(q["ITC"]["prev_close"], 273.9)
        self.assertEqual(q["INFY"]["price"], 1128.2)
        self.assertIsNotNone(q["INFY"]["delivery_pct"])

    def test_yahoo_parse(self):
        data = {"chart": {"result": [{"meta": {"regularMarketPrice": 281.5, "chartPreviousClose": 270,
                                                "regularMarketTime": 1793863000, "currency": "INR"},
                                       "indicators": {"quote": [{"close": [275.0, 280.0, 281.5]}]}}]}}
        q = alerts.parse_yahoo(data, "ITC")
        self.assertEqual((q["price"], q["prev_close"]), (281.5, 280.0))
        self.assertEqual(alerts.yahoo_symbol("ITC"), "ITC.NS")
        self.assertEqual(alerts.yahoo_symbol("ITC", "BSE"), "ITC.BO")

    def test_rules_ring_once_and_rearm(self):
        now = dt.datetime(2026, 11, 5, 11, 0, tzinfo=T.IST)
        rules = [{"id": 1, "symbol": "ITC", "kind": "below", "level": 285},
                 {"id": 2, "symbol": "ITC", "kind": "move-pct", "level": 2},
                 {"id": 3, "symbol": "BELL", "kind": "bell", "level": None}]
        state = {}
        q = {"ITC": {"price": 280.0, "prev_close": 273.9}}
        with TraderDir():
            self.assertEqual(sorted(r["id"] for r, _ in alerts.evaluate(rules, q, now, state)), [1, 2, 3])
            self.assertEqual(alerts.evaluate(rules, q, now, state), [])
            alerts.evaluate(rules, {"ITC": {"price": 290.0, "prev_close": 273.9}}, now, state)   # re-arms #1
            rang = alerts.evaluate(rules, q, now, state)
            self.assertEqual([r["id"] for r, _ in rang], [1])


if __name__ == "__main__":
    unittest.main()
