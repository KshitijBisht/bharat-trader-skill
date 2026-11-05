"""Shared helpers for the Bharat Trader skills.

Standard library only. Every skill script adds this folder to sys.path, so the
skill folders must stay siblings of trader-common/ (they do when you install the
plugin or `cp -r bharat-trader-skill/trader-* ~/.claude/skills/`).

What lives here:
  * the trader/ working folder and config defaults
  * a polite HTTP client (browser user agent, NSE cookie warm-up, rate limit)
  * Indian equity delivery charges (Groww's published schedule by default)
  * IST time, the NSE trading calendar and session times
  * the Groww place_order shape and order fingerprints
"""

import datetime as _dt
import gzip
import hashlib
import http.cookiejar
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0.0"

# --------------------------------------------------------------------------
# working folder and config
# --------------------------------------------------------------------------

DEFAULTS = {
    "budget": 10000,
    "cash_buffer_pct": 5,
    "max_position_pct": 25,
    "max_order_inr": 5000,
    "min_order_inr": 100,
    "max_orders_per_day": 10,
    "max_charges_pct": 2.5,
    "broker": "groww",
    "paper": True,
    "exchange": "NSE",
    "product": "CNC",
    "order_type": "MARKET",
    "blocked": [],
    "allow_intraday": False,
    "allow_fno": False,
    "allow_mtf": False,
    "allow_short": False,
    "allow_sme": False,
    "allow_surveillance": False,
    "allow_t2t": False,
    "charges": {},
    "tax": {},
}


def trader_dir():
    """The trader/ folder every skill reads and writes (TRADER_DIR overrides)."""
    return os.environ.get("TRADER_DIR") or os.path.join(os.getcwd(), "trader")


def path(name):
    return os.path.join(trader_dir(), name)


def load_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise SystemExit("%s is not valid JSON: %s" % (p, exc))


def save_json(p, data):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, p)


def config(p=None):
    cfg = dict(DEFAULTS)
    user = load_json(p or path("config.json"), {}) or {}
    cfg.update(user)
    return cfg


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(code)


# --------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------

def inr(x, decimals=2):
    """Format rupees the Indian way: 12,34,567.89."""
    neg = x < 0
    scale = 10 ** decimals
    whole, frac = divmod(int(round(abs(float(x)) * scale)), scale)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    if decimals:
        s += "." + str(frac).zfill(decimals)
    neg = neg and (whole or frac)
    return ("-₹" if neg else "₹") + s


def num(v, default=None):
    """Parse '1,23,456.70', '-', '', None into a float."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("₹", "")
    if s in ("", "-", "NA", "N/A", "nil", "Nil", "null"):
        return default
    try:
        return float(s)
    except ValueError:
        return default


# --------------------------------------------------------------------------
# charges: equity delivery (CNC) on Groww, from groww.in/pricing
# --------------------------------------------------------------------------

GROWW_DELIVERY = {
    "source": "https://groww.in/pricing",
    "last_verified": "2026-11-05",
    "brokerage_pct": 0.1,          # 0.1% per executed order ...
    "brokerage_max": 20.0,         # ... or Rs 20, whichever is lower
    "brokerage_min": 5.0,          # ... minimum Rs 5
    "stt_pct": 0.1,                # delivery: 0.1% on buy and on sell
    "stamp_buy_pct": 0.015,        # delivery: 0.015% on buy only
    "exchange_pct": {"NSE": 0.00297, "BSE": 0.00375},
    "sebi_pct": 0.0001,
    "ipft_pct": {"NSE": 0.0001, "BSE": 0.0},
    "dp_sell": 20.0,               # Rs 3.5 depository + Rs 16.5 Groww, per scrip per day of sale
    "dp_free_below": 100.0,        # no DP charge when the debit value is under Rs 100
    "gst_pct": 18.0,               # on brokerage, exchange, SEBI, IPFT and DP
}


def charge_schedule(cfg=None):
    sched = dict(GROWW_DELIVERY)
    if cfg and cfg.get("charges"):
        sched.update(cfg["charges"])
    return sched


def charges(side, value, exchange="NSE", cfg=None, dp=True):
    """Every rupee a single delivery order costs on top of (or out of) its value.

    side: "BUY" or "SELL". value: quantity x price in rupees. dp: charge the DP
    fee (once per scrip per day of sale) on this sell.
    """
    s = charge_schedule(cfg)
    side = side.upper()
    exchange = (exchange or "NSE").upper()
    value = float(value)
    if value <= 0:
        return {"brokerage": 0.0, "stt": 0.0, "stamp": 0.0, "exchange": 0.0, "sebi": 0.0,
                "ipft": 0.0, "dp": 0.0, "gst": 0.0, "total": 0.0}
    brokerage = min(s["brokerage_max"], max(s["brokerage_min"], value * s["brokerage_pct"] / 100))
    brokerage = min(brokerage, value)
    stt = math.floor(value * s["stt_pct"] / 100 + 0.5)   # nearest rupee, halves up
    stamp = round(value * s["stamp_buy_pct"] / 100, 2) if side == "BUY" else 0.0
    exch = value * _pick(s["exchange_pct"], exchange) / 100
    sebi = value * s["sebi_pct"] / 100
    ipft = value * _pick(s["ipft_pct"], exchange) / 100
    dp_fee = s["dp_sell"] if (side == "SELL" and dp and value >= s["dp_free_below"]) else 0.0
    gst = (brokerage + exch + sebi + ipft + dp_fee) * s["gst_pct"] / 100
    out = {"brokerage": brokerage, "stt": float(stt), "stamp": stamp, "exchange": exch,
           "sebi": sebi, "ipft": ipft, "dp": dp_fee, "gst": gst}
    out = {k: round(v, 2) for k, v in out.items()}
    out["total"] = round(sum(out.values()), 2)
    return out


def _pick(v, exchange):
    return v.get(exchange, 0.0) if isinstance(v, dict) else float(v)


def round_trip_pct(value, exchange="NSE", cfg=None):
    """Charges to buy `value` today and sell it later at the same price, as % of value."""
    if value <= 0:
        return 0.0
    c = charges("BUY", value, exchange, cfg)["total"] + charges("SELL", value, exchange, cfg)["total"]
    return round(100.0 * c / value, 3)


# --------------------------------------------------------------------------
# IST, the NSE calendar and sessions
# --------------------------------------------------------------------------

IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30), "IST")

# NSE capital-market trading holidays, from nseindia.com/api/holiday-master?type=trading
# (fetched 2026-11-05). Weekend dates are listed by NSE too and kept for completeness.
NSE_HOLIDAYS = {
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-02-15": "Mahashivratri",
    "2026-03-03": "Holi",
    "2026-03-21": "Id-Ul-Fitr (Ramadan Eid)",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan (Muhurat trading session, timings announced by NSE)",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}

SESSION = {
    "pre_open_start": (9, 0),
    "pre_open_end": (9, 8),       # order entry closes; matching till ~9:12, then buffer
    "open": (9, 15),
    "close": (15, 30),
    "post_close_end": (16, 0),
}


def now_ist():
    fixed = os.environ.get("TRADER_NOW")   # tests: "2026-11-05T10:00"
    if fixed:
        return _dt.datetime.fromisoformat(fixed).replace(tzinfo=IST)
    return _dt.datetime.now(IST)


def holidays():
    """Built-in 2026 list plus anything cached by `alerts.py holidays --fetch`."""
    h = dict(NSE_HOLIDAYS)
    cached = load_json(path("holidays.json"), {}) or {}
    h.update(cached.get("CM", {}) if isinstance(cached.get("CM"), dict) else {})
    return h


def is_trading_day(d):
    if isinstance(d, _dt.datetime):
        d = d.date()
    return d.weekday() < 5 and d.isoformat() not in holidays()


def next_trading_day(d):
    if isinstance(d, _dt.datetime):
        d = d.date()
    d = d + _dt.timedelta(days=1)
    while not is_trading_day(d):
        d += _dt.timedelta(days=1)
    return d


def market_state(t=None):
    """'pre-open', 'open', 'post-close', 'closed' or 'holiday' with the next open."""
    t = t or now_ist()
    t = t.astimezone(IST)
    d = t.date()
    hm = (t.hour, t.minute)
    if not is_trading_day(d):
        reason = holidays().get(d.isoformat(), "weekend")
        nxt = next_trading_day(d)
        return {"state": "holiday" if d.isoformat() in holidays() else "closed", "reason": reason,
                "next_open": "%s 09:15 IST" % nxt.isoformat()}
    if hm < SESSION["pre_open_start"]:
        return {"state": "closed", "reason": "before pre-open", "next_open": "%s 09:15 IST" % d}
    if hm < SESSION["open"]:
        return {"state": "pre-open", "reason": "pre-open session (09:00-09:15)",
                "next_open": "%s 09:15 IST" % d}
    if hm < SESSION["close"]:
        return {"state": "open", "reason": "normal market (09:15-15:30)", "closes": "%s 15:30 IST" % d}
    nxt = next_trading_day(d)
    if hm < SESSION["post_close_end"]:
        return {"state": "post-close", "reason": "closing session (15:40-16:00, at close price)",
                "next_open": "%s 09:15 IST" % nxt}
    return {"state": "closed", "reason": "after hours", "next_open": "%s 09:15 IST" % nxt}


def parse_date(s):
    """'04-Nov-2026', '04-NOV-2026', '2026-11-04', '04-11-2026', '04-Nov-2026 21:01:36'."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y"):
        try:
            return _dt.datetime.strptime(s.title() if "%b" in fmt else s, fmt)
        except ValueError:
            continue
    return None


def financial_year(d):
    """Indian FY label for a date: 2026-11-05 -> 'FY2026-27'."""
    if isinstance(d, str):
        d = _dt.date.fromisoformat(d[:10])
    start = d.year if d.month >= 4 else d.year - 1
    return "FY%d-%02d" % (start, (start + 1) % 100)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
_last = {}
_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_nse_warm = [False]
MIN_GAP = {"www.nseindia.com": 0.4, "nsearchives.nseindia.com": 0.3}


def http_get(url, referer=None, accept="*/*", retries=3, timeout=30):
    """GET bytes. Polite: browser UA, gzip, per-host gap, retries on 429/5xx."""
    host = urllib.parse.urlparse(url).netloc
    if host == "www.nseindia.com" and not _nse_warm[0]:
        _nse_warm[0] = True
        try:
            _fetch("https://www.nseindia.com/", None, "text/html", 15)
        except Exception:
            pass            # the home page often returns 403; the API cookies still get set
    last_err = None
    for attempt in range(retries):
        gap = MIN_GAP.get(host, 0.2)
        wait = _last.get(host, 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        try:
            return _fetch(url, referer or ("https://www.nseindia.com/" if "nseindia" in host else None),
                          accept, timeout)
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            if exc.code in (401, 403) and host == "www.nseindia.com" and attempt == 0:
                _nse_warm[0] = False
                continue
            raise
        except urllib.error.URLError as exc:
            last_err = exc
            time.sleep(1.0 * (attempt + 1))
    raise last_err


def _fetch(url, referer, accept, timeout):
    headers = {"User-Agent": UA, "Accept": accept, "Accept-Language": "en-IN,en;q=0.9",
               "Accept-Encoding": "gzip"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with _opener.open(req, timeout=timeout) as resp:
        data = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data


def http_json(url, **kw):
    data = http_get(url, accept="application/json, text/plain, */*", **kw)
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("not JSON from %s (NSE may be blocking; try again later): %r"
                         % (url, data[:120]))


def http_text(url, **kw):
    data = http_get(url, **kw)
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def read_source(src):
    """A local file path or a URL -> bytes. Lets every parser run offline."""
    if src.startswith(("http://", "https://")):
        return http_get(src)
    with open(src, "rb") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# NSE symbol master and prices on disk
# --------------------------------------------------------------------------

EQUITY_L = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def equity_list(src=None):
    """{symbol: {name, series, isin, lot}} from NSE's EQUITY_L.csv (cached in trader/)."""
    import csv
    cache = path("EQUITY_L.csv")
    if src is None:
        src = cache if os.path.exists(cache) else EQUITY_L
    raw = read_source(src)
    if src == EQUITY_L:
        os.makedirs(trader_dir(), exist_ok=True)
        with open(cache, "wb") as fh:
            fh.write(raw)
    rows = csv.reader(io.StringIO(raw.decode("utf-8", "replace")))
    header = [h.strip().upper() for h in next(rows)]
    out = {}
    for r in rows:
        if not r:
            continue
        rec = dict(zip(header, [c.strip() for c in r]))
        sym = rec.get("SYMBOL")
        if sym:
            out[sym] = {"name": rec.get("NAME OF COMPANY", ""), "series": rec.get("SERIES", ""),
                        "isin": rec.get("ISIN NUMBER", ""), "lot": int(num(rec.get("MARKET LOT"), 1))}
    return out


def isin_map(eq):
    return {v["isin"]: k for k, v in eq.items() if v.get("isin")}


def prices(p=None):
    """{symbol: price} from trader/prices.json (written by trader-alerts)."""
    data = load_json(p or path("prices.json"), {}) or {}
    q = data.get("quotes", data)
    out = {}
    for k, v in q.items():
        out[k.upper()] = num(v.get("price") if isinstance(v, dict) else v)
    return {k: v for k, v in out.items() if v}


# --------------------------------------------------------------------------
# orders
# --------------------------------------------------------------------------

ORDER_KEYS = ("trading_symbol", "quantity", "price", "trigger_price", "validity", "exchange",
              "segment", "product", "order_type", "transaction_type")


def groww_order(symbol, qty, side, cfg=None, order_type=None, price=None, exchange=None):
    """An order in the exact argument shape of growwapi.GrowwAPI.place_order."""
    cfg = cfg or DEFAULTS
    ot = (order_type or cfg.get("order_type") or "MARKET").upper()
    return {
        "trading_symbol": symbol.upper(),
        "quantity": int(qty),
        "price": float(price) if (ot in ("LIMIT", "SL") and price) else 0.0,
        "trigger_price": None,
        "validity": "DAY",
        "exchange": (exchange or cfg.get("exchange") or "NSE").upper(),
        "segment": "CASH",
        "product": (cfg.get("product") or "CNC").upper(),
        "order_type": ot,
        "transaction_type": side.upper(),
    }


def fingerprint(order):
    core = {k: order.get(k) for k in ORDER_KEYS}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def reference_id(order, day=None):
    """Groww's order_reference_id: 8-20 alphanumerics, at most two hyphens."""
    day = day or now_ist().strftime("%Y%m%d")
    return ("BT%s-%s" % (day[2:], fingerprint(order)[:8])).upper()


def table(rows, headers):
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    widths = [max(len(str(h)), *(len(r[i]) for r in rows)) if rows else len(str(h))
              for i, h in enumerate(headers)]
    line = "  ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    out = [line, "  ".join("-" * w for w in widths)]
    for r in rows:
        out.append("  ".join(c.rjust(w) if _numeric(c) else c.ljust(w) for c, w in zip(r, widths)))
    return "\n".join(out)


def _numeric(c):
    c = c.replace("₹", "").replace(",", "").replace("%", "").replace("+", "").replace("-", "", 1)
    try:
        float(c)
        return True
    except ValueError:
        return False
