"""Portable JSON data store. Same JSON schema as the Android app, so backups can be moved between the two."""
import json
import os
import random
import shutil
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
import layout
from pdf import exe_dir

SCHEMA = 1
APP = "StoreInvoiceGenerator"
DEFAULT_TYPES = [("Trimmer", "85102000"), ("Wired Earphone", "85183020"), ("Neckband", "85183020"), ("Headset", "85183010"), ("Wireless Earphone", "85183020")]
PARTY = ["name", "addr1", "addr2", "city", "state", "pin", "phone", "email"]


def dec_ok(s, lo=None, hi=None):
    try:
        v = Decimal(str(s).strip())
    except InvalidOperation:
        return None
    if lo is not None and v < lo:
        return None
    if hi is not None and v > hi:
        return None
    return v


class Repo:
    def __init__(self):
        self.root = os.path.join(exe_dir(), "StoreInvoiceData")
        self.backup_dir = os.path.join(self.root, "backups")
        self.pdf_dir = os.path.join(self.root, "invoices")
        for d in (self.root, self.backup_dir, self.pdf_dir):
            os.makedirs(d, exist_ok=True)
        self.file = os.path.join(self.root, "data.json")
        self.types, self.products, self.customers, self.invoices = [], [], [], []
        self.store = dict(name="Parkar", addr1="Nmum-Kharghar-A116", addr2="Navi Mumbai-410210", addr3="", phone="18099985662/040-49462310",
                          gst="27ADFFGHHH6H1ZE", **layout.DEFAULTS)
        self.settings = dict(till="1100", createdBy="Vignesh Patil", payment="UPI", taxMode="INCLUSIVE")
        loaded = False
        if os.path.exists(self.file):
            try:
                with open(self.file, encoding="utf-8") as f:
                    self._apply(json.load(f), False); loaded = True
            except Exception:
                shutil.copy(self.file, os.path.join(self.backup_dir, f"corrupt_{int(time.time())}.json"))
        if not self.types:
            self.types = [dict(name=n, hsn=h, cgst="9", sgst="9") for n, h in DEFAULT_TYPES]
        if not loaded:
            self.save()

    # ----- ids / numbers
    def new_id(self):
        return f"{int(time.time() * 1000):x}{random.randrange(4096):03x}"

    def digits(self, n):
        return "".join(random.SystemRandom().choice("0123456789") for _ in range(n))

    def new_product_code(self):
        while True:
            c = str(random.SystemRandom().randrange(100000, 1000000))
            if all(p["code"] != c for p in self.products):
                return c

    def new_order_no(self):
        while True:
            o = "SOA" + self.digits(12)
            if all(i["orderNo"] != o for i in self.invoices):
                return o

    def new_txn_id(self):
        return "RT" + self.digits(15)

    @staticmethod
    def now():
        return datetime.now().strftime("%d/%m/%Y %H:%M")

    def type_of(self, name):
        return next((t for t in self.types if t["name"] == name), None)

    # ----- persistence
    def to_json(self):
        return dict(schemaVersion=SCHEMA, app=APP, exportedAt=int(time.time() * 1000), productTypes=self.types,
                    products=[dict(id=p["id"], type=p["type"], name=p["name"], code=p["code"], unitPrice=p["price"], cgst=p["cgst"], sgst=p["sgst"], imageUrl=p["image"]) for p in self.products],
                    customers=[dict(id=c["id"], **{k: c.get(k, "") for k in PARTY}) for c in self.customers],
                    store=dict(name=self.store["name"], addr1=self.store["addr1"], addr2=self.store["addr2"], addr3=self.store["addr3"], phone=self.store["phone"], gst=self.store["gst"],
                               **{k: self.store[k] for k in layout.DEFAULTS}),
                    settings=self.settings, invoices=self.invoices)

    def save(self):
        tmp = self.file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.file)

    def _apply(self, j, merge):
        if not merge:
            self.types, self.products, self.customers, self.invoices = [], [], [], []
        for t in j["productTypes"]:
            if all(x["name"] != t["name"] for x in self.types):
                self.types.append(dict(name=t["name"], hsn=t.get("hsn", ""), cgst=str(t["cgst"]), sgst=str(t["sgst"])))
        for p in j["products"]:
            if all(x["id"] != p["id"] for x in self.products):
                self.products.append(dict(id=p["id"], type=p.get("type", ""), name=p["name"], code=p.get("code", ""), price=str(p["unitPrice"]), cgst=str(p["cgst"]), sgst=str(p["sgst"]), image=p.get("imageUrl", "")))
        for c in j["customers"]:
            if all(x["id"] != c["id"] for x in self.customers):
                self.customers.append(dict(id=c["id"], **{k: c.get(k, "") for k in PARTY}))
        for v in j["invoices"]:
            if all(x["orderNo"] != v["orderNo"] for x in self.invoices):
                d = dict(layout.DEFAULTS); d.update(v["data"]); v = dict(v); v["data"] = d; self.invoices.append(v)
        if not merge:
            s = j["store"]
            self.store = dict(name=s.get("name", ""), addr1=s.get("addr1", ""), addr2=s.get("addr2", ""), addr3=s.get("addr3", ""), phone=s.get("phone", ""), gst=s.get("gst", ""),
                              **{k: s.get(k, v) for k, v in layout.DEFAULTS.items()})
            t = j["settings"]
            self.settings = dict(till=t.get("till", "1100"), createdBy=t.get("createdBy", ""), payment=t.get("payment", "UPI"), taxMode=t.get("taxMode", "INCLUSIVE"))

    def validate(self, j):
        """None if valid, otherwise a readable problem."""
        try:
            if j.get("app") != APP:
                return "Not a Store Invoice Generator backup."
            if int(j["schemaVersion"]) > SCHEMA:
                return "Backup was made by a newer app version."
            for k in ("productTypes", "products", "customers", "invoices"):
                if not isinstance(j[k], list):
                    return f"'{k}' is missing."
            if not j["productTypes"]:
                return "No product types in file."
            if not isinstance(j["store"], dict) or not isinstance(j["settings"], dict):
                return "Store or settings section is missing."
            for t in j["productTypes"]:
                t["name"]; Decimal(str(t["cgst"])); Decimal(str(t["sgst"]))
            for p in j["products"]:
                p["id"]; p["name"]; Decimal(str(p["unitPrice"])); Decimal(str(p["cgst"])); Decimal(str(p["sgst"]))
            for c in j["customers"]:
                c["id"]
            for v in j["invoices"]:
                v["orderNo"]; d = v["data"]; d["items"]; d["customer"]; d["transactionId"]; d["dateTime"]
                for it in d["items"]:
                    Decimal(str(it["unit"])); int(it["qty"])
        except Exception as e:
            return f"Invalid backup file: {e!r}"
        return None

    def backup(self, label="backup"):
        f = os.path.join(self.backup_dir, f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(self.to_json(), fh, indent=2, ensure_ascii=False)
        return f

    def backups(self):
        return sorted((f for f in os.listdir(self.backup_dir) if f.endswith(".json") and not f.startswith("corrupt")), reverse=True)

    def import_text(self, text, merge):
        """Validates, takes a safety backup, then merges or replaces. Returns an error string or None."""
        try:
            j = json.loads(text)
        except Exception:
            return "File is not valid JSON."
        err = self.validate(j)
        if err:
            return err
        self.backup("before-import")
        self._apply(j, merge); self.save()
        return None

    # ----- invoice snapshot helpers
    def pdf_path(self, order_no):
        return os.path.join(self.pdf_dir, f"{order_no}.pdf")
