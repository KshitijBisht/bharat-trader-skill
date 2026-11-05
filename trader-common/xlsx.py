"""Read the first (or a named) sheet of an .xlsx file with the standard library only.

Mutual-fund monthly portfolio disclosures are published as .xlsx by most AMCs.
Old binary .xls files are not supported: open and re-save them as .xlsx.
"""

import io
import re
import zipfile
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def sheets(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = []
    for s in wb.find("m:sheets", NS):
        rid = s.get("{%s}id" % NS["r"])
        t = target[rid].lstrip("/")
        out.append((s.get("name"), t if t.startswith("xl/") else "xl/" + t))
    return out


def rows(data, sheet=None):
    """List of rows, each a list of cell strings (empty string for blanks)."""
    if not data.startswith(b"PK"):
        raise ValueError("not an .xlsx file (old .xls? open it and save as .xlsx)")
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    names = sheets(data)
    path = names[0][1]
    if sheet is not None:
        for n, p in names:
            if n == sheet:
                path = p
    root = ET.fromstring(z.read(path))
    out = []
    for row in root.iter("{%s}row" % NS["m"]):
        cells = {}
        for c in row.findall("m:c", NS):
            ref = c.get("r")
            t = c.get("t")
            v = c.find("m:v", NS)
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            else:
                val = v.text if v is not None else ""
            cells[_col(ref)] = (val or "").strip()
        if cells:
            width = max(cells) + 1
            out.append([cells.get(i, "") for i in range(width)])
        else:
            out.append([])
    return out
