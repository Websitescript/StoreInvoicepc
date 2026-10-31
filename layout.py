"""Invoice engine: calculation + page layout (port of the Android app, produces identical draw commands)."""
import re
from decimal import Decimal, ROUND_HALF_UP

PAGE_W, PAGE_H = 216.0, 842.5
FONT, ASCENT, PITCH, Y0, SLOTS, GROUP_H = 8.5, 7.08, 10.52, 2.8, 80, 114.0
X1, X2 = -0.75, -0.25

DEFAULTS = dict(legal="Falah Retail Limited Trading as", cin="U31988MH2020PLC998115",
                regd1="Regd. Office - Unit No. 701 & 702,", regd2="7th Floor, Khed,", regd3="Ratnagiri,  415710,India",
                site="falah.com", email="customersupport@falah.com")

_T = ["11011001100","11001101100","11001100110","10010011000","10010001100","10001001100","10011001000","10011000100","10001100100","11001001000","11001000100","11000100100","10110011100","10011011100","10011001110","10111001100","10011101100","10011100110","11001110010","11001011100","11001001110","11011100100","11001110100","11101101110","11101001100","11100101100","11100100110","11101100100","11100110100","11100110010","11011011000","11011000110","11000110110","10100011000","10001011000","10001000110","10110001000","10001101000","10001100010","11010001000","11000101000","11000100010","10110111000","10110001110","10001101110","10111011000","10111000110","10001110110","11101110110","11010001110","11000101110","11011101000","11011100010","11011101110","11101011000","11101000110","11100010110","11101101000","11101100010","11100011010","11101111010","11001000010","11110001010","10100110000","10100001100","10010110000","10010000110","10000101100","10000100110","10110010000","10110000100","10011010000","10011000010","10000110100","10000110010","11000010010","11001010000","11110111010","11000010100","10001111010","10100111100","10010111100","10010011110","10111100100","10011110100","10011110010","11110100100","11110010100","11110010010","11011011110","11011110110","11110110110","10101111000","10100011110","10001011110","10111101000","10111100010","11110101000","11110100010","10111011110","10111101110","11101011110","11110101110","11010000100","11010010000","11010011100", "1100011101011"]


def D(v):
    return v if isinstance(v, Decimal) else Decimal(str(v).strip() or "0")


def r2(v):
    return D(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(v):
    return format(r2(v), "f")


def rate4(v):
    return format(D(v).quantize(Decimal("0.0001")), "f")


# ---------------- Code 128 (subsets B and C) ----------------
def code128(text):
    segs, i, n, sb = [], 0, len(text), ""
    while i < n:
        j = i
        while j < n and text[j] in "0123456789":
            j += 1
        run = j - i
        if run >= 4 and (i == 0 or run >= 6 or j == n):
            s = i
            if run % 2 == 1:
                sb += text[s]; s += 1
            if sb:
                segs.append(("B", sb)); sb = ""
            segs.append(("C", text[s:j])); i = j
        else:
            e = j if run > 0 else i + 1
            sb += text[i:e]; i = e
    if sb:
        segs.append(("B", sb))
    codes, cur = [], ""
    for k, seg in segs:
        if k != cur:
            codes.append((105 if k == "C" else 104) if not codes else (99 if k == "C" else 100)); cur = k
        if k == "C":
            codes += [int(seg[p:p + 2]) for p in range(0, len(seg), 2)]
        else:
            codes += [ord(ch) - 32 for ch in seg]
    codes.append(sum(codes[0:1] + [c * p for p, c in enumerate(codes) if p > 0]) % 103)
    codes.append(106)
    return [ch == "1" for c in codes for ch in _T[c]]


# ---------------- Tax calculation ----------------
def compute(items, tax_mode):
    """items: dicts with qty, unit, cgst, sgst. INCLUSIVE extracts tax from the price; ORIGINAL = rate x gross like the legacy system."""
    lines = []
    for it in items:
        total = r2(D(it["unit"]) * int(it["qty"]))
        c, s = D(it["cgst"]), D(it["sgst"])
        if tax_mode == "ORIGINAL":
            lines.append(dict(item=it, total=total, taxable=total, cgst=r2(total * c / 100), sgst=r2(total * s / 100)))
        else:
            t0 = (total * 100 / (100 + c + s)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ca, sa = r2(t0 * c / 100), r2(t0 * s / 100)
            lines.append(dict(item=it, total=total, taxable=total - ca - sa, cgst=ca, sgst=sa))
    groups = {}
    for l in lines:
        g = groups.setdefault((D(l["item"]["cgst"]).normalize(), D(l["item"]["sgst"]).normalize()), dict(total=Decimal(0), cgst_amt=Decimal(0), sgst_amt=Decimal(0)))
        g["total"] += l["total"]; g["cgst_amt"] += l["cgst"]; g["sgst_amt"] += l["sgst"]
    z = Decimal(0)
    return dict(lines=lines, subtotal=sum((l["taxable"] for l in lines), z), cgst=sum((l["cgst"] for l in lines), z),
                sgst=sum((l["sgst"] for l in lines), z), grand=sum((l["total"] for l in lines), z),
                groups=[dict(cgst=k[0], sgst=k[1], **v) for k, v in groups.items()])


STATE_CODES = {"jammu and kashmir": 1, "himachal pradesh": 2, "punjab": 3, "chandigarh": 4, "uttarakhand": 5, "haryana": 6, "delhi": 7,
    "rajasthan": 8, "uttar pradesh": 9, "bihar": 10, "sikkim": 11, "arunachal pradesh": 12, "nagaland": 13, "manipur": 14, "mizoram": 15,
    "tripura": 16, "meghalaya": 17, "assam": 18, "west bengal": 19, "jharkhand": 20, "odisha": 21, "chhattisgarh": 22, "madhya pradesh": 23,
    "gujarat": 24, "dadra and nagar haveli and daman and diu": 26, "maharashtra": 27, "karnataka": 29, "goa": 30, "lakshadweep": 31,
    "kerala": 32, "tamil nadu": 33, "puducherry": 34, "andaman and nicobar islands": 35, "telangana": 36, "andhra pradesh": 37, "ladakh": 38}
STATE_NAMES = sorted(" ".join(w if w == "and" else w.capitalize() for w in k.split(" ")) for k in STATE_CODES)


def state_label(state):
    s = state.strip()
    if not s or "-" in s:
        return s
    c = STATE_CODES.get(s.lower())
    return s if c is None else f"{s}-{c}"


# ---------------- Layout ----------------
D1 = " " + "-" * 40
D2 = " " + "-" * 39 + " "


def center(s, w=41):
    return " " * max(0, (w - len(s) + 1) // 2) + s


def right(left, r, w=40):
    return left + " " * max(1, w - len(left) - len(r)) + r


def cols(*parts):
    c = [" "] * 40
    for at, s in parts:
        for k, ch in enumerate(s):
            if 0 <= at + k <= 39:
                c[at + k] = ch
    return "".join(c)


def rc(at, s):
    return (at - len(s) + 1, s)


def wrap(text, w):
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            while len(word) > w:
                if line:
                    out.append(line); line = ""
                out.append(word[:w]); word = word[w:]
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= w:
                line += " " + word
            else:
                out.append(line); line = word
        if line:
            out.append(line)
    return out


def _flow_rows(d, t):
    r = []  # (text, x, keep)

    def add(s, x=X1):
        r.append([s, x, 0])
    if d["legal"].strip():
        add(center(d["legal"], 39))
    if d["storeName"].strip():
        add(center(d["storeName"]))
    add(center("Tax Invoice"))
    for a in (d["sAddr1"], d["sAddr2"], d["sAddr3"]):
        if a.strip():
            for ln in wrap(a, 38):
                add(center(ln))
    ph = d["sPhone"].strip()
    sl = ph.find("/")
    if 0 <= sl < len(ph) - 1:
        first = "Phone Number : " + ph[:sl + 1].strip()
        add(center(first))
        add(" " * max(0, (41 - len(first) + 1) // 2 + 14) + ph[sl + 1:].strip())
    else:
        add(center("Phone Number : " + ph))
    add(center("GST No: " + d["gst"]))
    add(D1)
    add(" Till No:" + d["till"])
    add(" Order Number: " + d["orderNo"])
    add(" Created By: " + d["createdBy"])
    add(" Date & Time:" + d["dateTime"])
    add(D2)
    c = d["customer"]
    add("Bill to address:", X2)
    st = state_label(c.get("state", ""))
    for v in (c.get("name", ""), c.get("addr1", ""), c.get("addr2", ""), c.get("city", ""), st, c.get("pin", "")):
        if v.strip():
            for ln in wrap(v, 34):
                add("      " + ln)
    if c.get("phone", "").strip():
        add(c["phone"], X2)
    if c.get("email", "").strip():
        add(c["email"], X2)
    add("Place of Supply: " + st, X2)
    add(D1)
    add(" Item Description ")
    add(cols((1, "Item Code"), (19, "Tax"), rc(39, "Qty")))
    add(cols((1, "Price"), (16, "Total Amt"), rc(39, "Del_Type")))
    add(cols((1, "DemoY/N"), (17, "InstY/N"), (27, "Delivery Date")))
    add(" HSN CODE ")
    add(" SN/IMEI ")
    add(D1)
    add(" ------------- SELF-PICKUP --------------")
    add("       Invoice No: " + d["orderNo"])
    for l in t["lines"]:
        it = l["item"]
        start = len(r)
        for s in wrap("ZPLU - " + it["name"], 39):
            add(" " + s)
        add(" " + it["type"])
        add(cols((1, it["code"]), (18, "62/52"), rc(39, f'{it["qty"]}/EA')))
        add(cols((1, money(it["unit"])), (18, money(l["total"])), (36, "STOR")))
        add(cols((1, "NA"), (19, "NA"), (38, "NA")))
        add(" HSN CODE: " + it["hsn"])
        add("")
        r[start][2] = len(r) - start - 1
    add(D1)
    add(right(" TOTAL:", "INR " + money(t["grand"])))
    add(D1)
    add(center("Payment Details"))
    add(right(" " + d["payMethod"], "INR " + money(t["grand"])))
    add(" LastFourDigits: " + d["last4"])
    add(" Txn RefId: " + d["txnRef"])
    add("")
    add(D1)
    add(" Tax Summary ")
    add(cols((1, "Type"), (7, "Code"), (13, "Rate"), (21, "Total Amt"), (33, "Tax Amt")))
    for g in t["groups"]:
        add(cols((1, "SGST"), (7, "62"), (13, rate4(g["sgst"])), rc(29, money(g["total"])), rc(39, money(g["sgst_amt"]))))
        add(cols((1, "CGST"), (7, "52"), (13, rate4(g["cgst"])), rc(29, money(g["total"])), rc(39, money(g["cgst_amt"]))))
    add(" PRICES INCLUSIVE OF ALL TAXES ")
    add(D1)
    add(D1)
    if d["cin"].strip():
        add("       CIN : " + d["cin"])
    add("")
    if d["regd1"].strip():
        add("    " + d["regd1"] + " ")
    if d["regd2"].strip():
        add("     " + d["regd2"])
    if d["regd3"].strip():
        add("    " + d["regd3"])
    add(""); add("")
    add("          Thank you for shopping with us.", X2)
    add("        Buy yourself an electronics life,", X2)
    if d["site"].strip():
        s = "shop at " + d["site"]
        add(" " * max(0, 37 - len(s)) + s, X2)
    if d["email"].strip():
        s = "Email:" + d["email"]
        add(" " * max(0, 36 - len(s)) + s)
    return r


def _terms(site):
    cap = site[:1].upper() + site[1:]
    return [" " + "-" * 39 + "  ", "Exchange Policy / Terms and Conditions ", "",
        "1. Products that require Home Delivery ", "like LED TVs, Home Theatres, Air ", "Conditioners, Washing Machines, ",
        "Refrigerators etc will only be exchanged ", f"by {site} in case of inherent",
        "manufacturing or transit defects which ", "are found before, during or at the time ", "of demo/installation. Warranty period ",
        "for the product will start from the ", "date mentioned on the Invoice. ",
        "2. The product to be exchanged must be ", "returned without any scratches, dents, ", "tears or holes and with all the ",
        "accessories and manuals in the original ", "manufacturer's undamaged & saleable ", "box/packaging. ",
        "3. Any defects arising in the product ", "post-delivery and installation, will be ", "serviced by the manufacturer/brand ",
        "service center as per the ", "manufacturer's brand warranty policy. ", f"{cap} will facilitate the service from",
        "the respective manufacturer as per the ", "manufacturer's/brand's warranty items. ",
        "4. Personal Care products will not be ", "exchanged for hygiene reasons. ",
        "5. Free Gifts will not be ", "exchanged/replaced or covered under ", "any kind of warranty. ",
        "6. Wherever applicable, GST is levied at ", "applicable rate on the value determined ", "as per Rule 32(5) of the CGST Rules. ",
        "7. Whether tax payable on reverse ", "charge : No. ",
        "8. Please note that there would be ", "facilitation charges applicable for all ", "carry in products accepted at stores ",
        "for repairs or replacement. ", "-" * 39 + " "]


def build(d):
    """d: invoice dict (see store.py). Returns a list of pages; each page is a list of draw commands."""
    t = compute(d["items"], d["taxMode"])
    rows = _flow_rows(d, t)
    pages = [[]]
    cur = pages[0]
    slot = 0
    for text, x, keep in rows:
        if slot >= SLOTS or (keep > 0 and slot + keep + 1 > SLOTS):
            cur = []; pages.append(cur); slot = 0
        if text:
            cur.append(("t", x, Y0 + slot * PITCH, text))
        slot += 1
    base = Y0 + slot * PITCH
    if base + GROUP_H > PAGE_H:
        cur = []; pages.append(cur); base = Y0

    def at(o):
        return base + (o - 717.57)
    bt, bo = code128(d["transactionId"]), code128(d["orderNo"])
    cur += [("t", X1, at(717.57), D1), ("t", X1, at(728.32), center("Transaction ID", 41)),
            ("b", 108.0, at(737.84), 0.595, 23.6, bt), ("c", 108.0, at(768.9), d["transactionId"]),
            ("t", X1, at(778.07), " ---------"), ("t", 163.7, at(778.07), "--------"),
            ("t", X2, at(788.6), "----------"), ("t", 163.7, at(788.6), "--------"), ("t", X2, at(799.1), "-----"),
            ("b", 108.0, at(797.95), 0.595, 23.6, bo), ("c", 108.0, at(829.0), d["orderNo"]), ("t", 163.7, at(810.1), "Order ID")]
    tl = _terms(d["site"])
    ty, tc = base + GROUP_H + 4, cur
    if ty + len(tl) * PITCH > PAGE_H:
        tc = []; pages.append(tc); ty = 1.85
    for i, s in enumerate(tl):
        if s:
            tc.append(("t", X2, ty + i * PITCH, s))
    return pages
