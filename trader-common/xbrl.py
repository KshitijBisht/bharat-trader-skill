"""Minimal XBRL instance reader for the BSE/NSE taxonomies (in-bse-shp, in-bse-fin, in-capmkt).

facts(xml) -> {context_id: {tag: value}}. Units and decimals are ignored: Indian
exchange filings report rupees as plain numbers (see LevelOfRounding for display).
"""

import re
from xml.etree import ElementTree as ET


def facts(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    root = ET.fromstring(data)
    out = {}
    for el in root:
        tag = el.tag
        if not isinstance(tag, str) or "}" not in tag:
            continue
        ns, local = tag[1:].split("}", 1)
        if "xbrl.org/2003" in ns or "xbrl.org/2005" in ns or "xbrl.org/2006" in ns:
            continue
        ctx = el.get("contextRef")
        if ctx is None:
            continue
        out.setdefault(ctx, {})[local] = (el.text or "").strip()
    return out


def contexts(data):
    """{context_id: {"start": ..., "end": ..., "instant": ...}}"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    root = ET.fromstring(data)
    out = {}
    for el in root.iter("{http://www.xbrl.org/2003/instance}context"):
        p = el.find("{http://www.xbrl.org/2003/instance}period")
        rec = {}
        if p is not None:
            for k in ("startDate", "endDate", "instant"):
                x = p.find("{http://www.xbrl.org/2003/instance}" + k)
                if x is not None:
                    rec[k] = x.text
        out[el.get("id")] = rec
    return out


def first(f, tag, prefer=("MainD", "MainI", "OneD", "OneI")):
    for c in prefer:
        if tag in f.get(c, {}):
            return f[c][tag]
    for c, vals in f.items():
        if tag in vals:
            return vals[tag]
    return None


def instant_twin(ctx):
    """Shareholder names sit on 'D_<x>' (duration); their numbers on '<x>' (instant)."""
    return ctx[2:] if ctx.startswith("D_") else ctx


def norm_name(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper())
    return re.sub(r"\s+", " ", s).strip()
