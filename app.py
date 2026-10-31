"""Store Invoice Generator - Windows portable edition (tkinter)."""
import io
import json
import os
import sys
import threading
import tkinter as tk
import urllib.request
from decimal import Decimal
from tkinter import filedialog, messagebox, ttk

import layout
import pdf
from store import Repo, dec_ok

APP_TITLE = "Store Invoice Generator"
ACCENT = "#0F766E"
CUST_KEYS = ["name", "addr1", "addr2", "city", "state", "pin", "phone", "email"]
CUST_LABELS = ["Customer name", "Address line 1", "Address line 2", "City", "State", "PIN code", "Phone number", "Email ID"]


def inr(v):
    s = layout.money(v)
    whole, frac = s.split(".")
    neg = whole.startswith("-"); whole = whole.lstrip("-")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + "₹" + whole + "." + frac


def open_external(path, print_it=False):
    try:
        if hasattr(os, "startfile"):
            os.startfile(path, "print") if print_it else os.startfile(path)
        else:
            os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')
    except Exception as e:
        messagebox.showerror(APP_TITLE, f"Could not open the PDF: {e}")


class Scrollable(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")


def labeled(parent, row, col, label, var=None, kind="entry", values=None, width=34, readonly=False, colspan=1):
    """Label above the input, placed in a grid. Returns the input widget."""
    ttk.Label(parent, text=label, foreground="#52606D", font=("Segoe UI", 9, "bold")).grid(row=row, column=col, sticky="w", padx=6, pady=(8, 0), columnspan=colspan)
    if kind == "combo":
        w = ttk.Combobox(parent, textvariable=var, values=values or [], width=width - 2, state="readonly" if readonly else "normal")
    else:
        w = ttk.Entry(parent, textvariable=var, width=width)
    w.grid(row=row + 1, column=col, sticky="ew", padx=6, pady=(0, 2), columnspan=colspan)
    return w


def form_dialog(parent, title, fields, on_save, width=40):
    """fields: (key, label, initial, kind, values). on_save(values)->error string (stay open) or None (close)."""
    win = tk.Toplevel(parent); win.title(title); win.transient(parent); win.resizable(False, False)
    frm = ttk.Frame(win, padding=12); frm.pack(fill="both", expand=True)
    vars_, widgets = {}, {}
    for i, (key, label, initial, kind, values) in enumerate(fields):
        vars_[key] = tk.StringVar(value=initial)
        widgets[key] = labeled(frm, i * 2, 0, label, vars_[key], "combo" if kind in ("combo", "combo_edit") else "entry", values, width, readonly=(kind == "combo"))
    bar = ttk.Frame(frm); bar.grid(row=len(fields) * 2 + 1, column=0, sticky="e", pady=(12, 0))

    def save():
        err = on_save({k: v.get().strip() for k, v in vars_.items()})
        if err:
            messagebox.showerror(APP_TITLE, err, parent=win)
        else:
            win.destroy()
    ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right", padx=4)
    ttk.Button(bar, text="Save", command=save).pack(side="right", padx=4)
    win.bind("<Return>", lambda e: save()); win.bind("<Escape>", lambda e: win.destroy())
    win.grab_set(); win.focus_set()
    return win, vars_, widgets


class Table(ttk.Frame):
    def __init__(self, parent, columns, widths, height=14):
        super().__init__(parent)
        self.tree = ttk.Treeview(self, columns=[c for c, _ in columns], show="headings", height=height, selectmode="browse")
        for (c, t), w in zip(columns, widths):
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

    def fill(self, rows):
        self.tree.delete(*self.tree.get_children())
        for iid, vals in rows:
            self.tree.insert("", "end", iid=iid, values=vals)

    def selected(self):
        s = self.tree.selection()
        return s[0] if s else None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE); self.geometry("1180x760"); self.minsize(980, 640)
        self.repo = Repo()
        st = ttk.Style(self)
        try:
            st.theme_use("vista" if "vista" in st.theme_names() else "clam")
        except Exception:
            pass
        st.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        self.option_add("*Font", ("Segoe UI", 10))
        self.nb = ttk.Notebook(self); self.nb.pack(fill="both", expand=True)
        self.tabs = {}
        for key, name in [("home", "Dashboard"), ("invoice", "Create Invoice"), ("products", "Products"), ("customers", "Customers"),
                          ("history", "Invoice History"), ("store", "Store Settings"), ("types", "Product Types"), ("backup", "Backup & Restore")]:
            f = ttk.Frame(self.nb, padding=8); self.nb.add(f, text=f"  {name}  "); self.tabs[key] = f
        self.draft_vars = {}
        self.items = []
        self.build_home(); self.build_invoice(); self.build_products(); self.build_customers()
        self.build_history(); self.build_store(); self.build_types(); self.build_backup()
        self.new_draft()
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh())
        self.refresh()

    def goto(self, key):
        self.nb.select(self.tabs[key])

    def refresh(self):
        for fn in (self.refresh_home, self.refresh_products, self.refresh_customers, self.refresh_history, self.refresh_types, self.refresh_backup, self.refresh_cust_combo):
            fn()

    # ================= Dashboard =================
    def build_home(self):
        f = self.tabs["home"]
        ttk.Label(f, text=APP_TITLE, font=("Segoe UI", 20, "bold"), foreground=ACCENT).pack(anchor="w", pady=(4, 12))
        self.stat_lbl = {}
        row = ttk.Frame(f); row.pack(anchor="w")
        for k, t in (("inv", "Invoices generated"), ("prod", "Products"), ("cust", "Customers")):
            box = ttk.LabelFrame(row, text=t, padding=14); box.pack(side="left", padx=(0, 12))
            self.stat_lbl[k] = ttk.Label(box, text="0", font=("Segoe UI", 24, "bold"), foreground=ACCENT); self.stat_lbl[k].pack()
        ttk.Button(f, text="＋  Create new invoice", style="Accent.TButton", command=lambda: (self.new_draft(), self.goto("invoice"))).pack(anchor="w", pady=18, ipadx=14, ipady=6)
        self.path_lbl = ttk.Label(f, text="", foreground="#52606D"); self.path_lbl.pack(anchor="w")

    def refresh_home(self):
        self.stat_lbl["inv"].config(text=len(self.repo.invoices)); self.stat_lbl["prod"].config(text=len(self.repo.products)); self.stat_lbl["cust"].config(text=len(self.repo.customers))
        self.path_lbl.config(text=f"Data folder (portable, travels with the program):  {self.repo.root}")

    # ================= Create invoice =================
    def build_invoice(self):
        sc = Scrollable(self.tabs["invoice"]); sc.pack(fill="both", expand=True)
        body = sc.inner; body.columnconfigure(0, weight=1); body.columnconfigure(1, weight=1)
        names = ["name", "addr1", "addr2", "city", "state", "pin", "phone", "email"]
        v = self.draft_vars = {k: tk.StringVar() for k in
            names + ["till", "orderNo", "createdBy", "dateTime", "pay", "last4", "txnRef", "txnId", "legal", "storeName", "sAddr1", "sAddr2", "sAddr3", "sPhone", "gst", "cin", "regd1", "regd2", "regd3", "site", "email_s"]}
        cust = ttk.LabelFrame(body, text=" Customer ", padding=6); cust.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.cust_pick = tk.StringVar()
        self.cust_combo = labeled(cust, 0, 0, "Saved customer", self.cust_pick, "combo", [], readonly=True, colspan=2)
        self.cust_combo.bind("<<ComboboxSelected>>", self.pick_customer)
        for i, (k, lab) in enumerate(zip(names, CUST_LABELS)):
            r, c = 2 + (i // 2) * 2, i % 2
            labeled(cust, r, c, lab, v[k], "combo" if k == "state" else "entry", layout.STATE_NAMES if k == "state" else None, width=22)
        det = ttk.LabelFrame(body, text=" Invoice details ", padding=6); det.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        spec = [("Till number", "till"), ("Order number (SOA + 12 digits)", "orderNo"), ("Created by", "createdBy"), ("Date & time (dd/mm/yyyy hh:mm)", "dateTime"),
                ("Payment method", "pay"), ("Last four digits", "last4"), ("Transaction reference", "txnRef"), ("Transaction ID (barcode)", "txnId")]
        for i, (lab, k) in enumerate(spec):
            labeled(det, (i // 2) * 2, i % 2, lab, v[k], width=24)
        bar = ttk.Frame(det); bar.grid(row=9, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(bar, text="New order number", command=lambda: v["orderNo"].set(self.repo.new_order_no())).pack(side="left", padx=4)
        ttk.Button(bar, text="Date & time = now", command=lambda: v["dateTime"].set(self.repo.now())).pack(side="left", padx=4)
        sto = ttk.LabelFrame(body, text=" Store (this invoice only) ", padding=6); sto.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        sspec = [("Store name – line 1", "legal"), ("Store name – line 2", "storeName"), ("Address line 1", "sAddr1"), ("Address line 2", "sAddr2"), ("Address line 3", "sAddr3"),
                 ("Phone number", "sPhone"), ("GST number", "gst"), ("CIN number", "cin"), ("Regd. office line 1", "regd1"), ("Regd. office line 2", "regd2"),
                 ("Regd. office line 3", "regd3"), ("Website / brand name", "site"), ("Support email", "email_s")]
        for i, (lab, k) in enumerate(sspec):
            labeled(sto, (i // 3) * 2, i % 3, lab, v[k], width=30)
        for c in range(3):
            sto.columnconfigure(c, weight=1)
        pr = ttk.LabelFrame(body, text=" Products ", padding=6); pr.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        self.item_tbl = Table(pr, [("name", "Item"), ("type", "Type"), ("code", "Code"), ("hsn", "HSN"), ("tax", "CGST/SGST %"), ("qty", "Qty"), ("price", "Unit price (₹)"), ("total", "Total")],
                              [300, 120, 80, 90, 90, 50, 100, 100], height=7)
        self.item_tbl.pack(fill="both", expand=True)
        self.item_tbl.tree.bind("<Double-1>", lambda e: self.edit_item())
        ib = ttk.Frame(pr); ib.pack(fill="x", pady=6)
        for t, c in (("＋ Add product", self.add_item), ("Edit qty / price", self.edit_item), ("Remove", self.remove_item)):
            ttk.Button(ib, text=t, command=c).pack(side="left", padx=4)
        self.totals_lbl = ttk.Label(pr, text="", font=("Segoe UI", 10, "bold")); self.totals_lbl.pack(anchor="e", padx=8)
        act = ttk.Frame(body); act.grid(row=3, column=0, columnspan=2, sticky="e", padx=6, pady=10)
        ttk.Button(act, text="Clear / new invoice", command=self.new_draft).pack(side="left", padx=6)
        ttk.Button(act, text="Preview", command=self.preview_invoice).pack(side="left", padx=6)
        ttk.Button(act, text="Generate & Save PDF", style="Accent.TButton", command=self.save_invoice).pack(side="left", padx=6, ipadx=10, ipady=4)

    def refresh_cust_combo(self):
        self.cust_combo.config(values=["— Walk-in / type below —"] + [c["name"] for c in self.repo.customers])

    def pick_customer(self, _e=None):
        i = self.cust_combo.current()
        if i > 0:
            c = self.repo.customers[i - 1]
            for k in CUST_KEYS:
                self.draft_vars[k].set(c.get(k, ""))

    def new_draft(self):
        r, v, s = self.repo, self.draft_vars, self.repo.store
        for k in CUST_KEYS:
            v[k].set("")
        v["till"].set(r.settings["till"]); v["orderNo"].set(r.new_order_no()); v["createdBy"].set(r.settings["createdBy"]); v["dateTime"].set(r.now())
        v["pay"].set(r.settings["payment"]); v["last4"].set(r.digits(4)); v["txnRef"].set(r.digits(10)); v["txnId"].set(r.new_txn_id())
        for k, sk in (("legal", "legal"), ("storeName", "name"), ("sAddr1", "addr1"), ("sAddr2", "addr2"), ("sAddr3", "addr3"), ("sPhone", "phone"), ("gst", "gst"), ("cin", "cin"),
                      ("regd1", "regd1"), ("regd2", "regd2"), ("regd3", "regd3"), ("site", "site"), ("email_s", "email")):
            v[k].set(s[sk])
        self.cust_pick.set(""); self.items = []; self.refresh_items()

    def load_draft(self, d):
        self.new_draft(); v = self.draft_vars
        for k in CUST_KEYS:
            v[k].set(d["customer"].get(k, ""))
        for k in ("till", "orderNo", "createdBy", "dateTime", "last4", "txnRef", "legal", "storeName", "sAddr1", "sAddr2", "sAddr3", "sPhone", "gst", "cin", "regd1", "regd2", "regd3", "site"):
            v[k].set(d.get(k, ""))
        v["pay"].set(d["payMethod"]); v["txnId"].set(d["transactionId"]); v["email_s"].set(d.get("email", ""))
        self.items = [dict(name=i["name"], type=i["type"], code=i["code"], hsn=i["hsn"], cgst=str(i["cgst"]), sgst=str(i["sgst"]), qty=int(i["qty"]), price=str(i["unit"])) for i in d["items"]]
        self.refresh_items(); self.goto("invoice")

    def refresh_items(self):
        rows, items = [], []
        for n, it in enumerate(self.items):
            up = dec_ok(it["price"]) or Decimal(0)
            tot = layout.r2(up * max(it["qty"], 0))
            rows.append((str(n), (it["name"], it["type"], it["code"], it["hsn"], f'{it["cgst"]}/{it["sgst"]}', it["qty"], layout.money(up), layout.money(tot))))
            items.append(dict(qty=max(it["qty"], 0), unit=up, cgst=it["cgst"], sgst=it["sgst"]))
        self.item_tbl.fill(rows)
        t = layout.compute(items, self.repo.settings["taxMode"])
        self.totals_lbl.config(text=f'Subtotal (taxable) {inr(t["subtotal"])}     CGST {inr(t["cgst"])}     SGST {inr(t["sgst"])}     GRAND TOTAL {inr(t["grand"])}')

    def add_item(self):
        if not self.repo.products:
            messagebox.showinfo(APP_TITLE, "No products yet – add them in the Products tab first."); return
        win = tk.Toplevel(self); win.title("Select product"); win.transient(self); win.geometry("560x420"); win.grab_set()
        q = tk.StringVar()
        ttk.Label(win, text="Search products", foreground="#52606D", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        e = ttk.Entry(win, textvariable=q); e.pack(fill="x", padx=10); e.focus_set()
        lb = tk.Listbox(win, height=14); lb.pack(fill="both", expand=True, padx=10, pady=8)
        shown = []

        def fill(*_):
            shown.clear(); lb.delete(0, "end")
            for p in self.repo.products:
                if q.get().lower() in f'{p["name"]} {p["type"]} {p["code"]}'.lower():
                    shown.append(p); lb.insert("end", f'{p["name"]}   |   {p["type"]}   |   {p["code"]}   |   {inr(dec_ok(p["price"]) or 0)}')
        q.trace_add("write", fill); fill()

        def pick(_e=None):
            if not lb.curselection():
                return
            p = shown[lb.curselection()[0]]
            ex = next((i for i in self.items if i["code"] == p["code"]), None)
            if ex:
                ex["qty"] += 1
            else:
                t = self.repo.type_of(p["type"])
                self.items.append(dict(name=p["name"], type=p["type"], code=p["code"], hsn=t["hsn"] if t else "", cgst=p["cgst"], sgst=p["sgst"], qty=1, price=p["price"]))
            self.refresh_items(); win.destroy()
        lb.bind("<Double-1>", pick); win.bind("<Return>", pick)
        ttk.Button(win, text="Add to invoice", command=pick).pack(pady=(0, 10))

    def edit_item(self):
        sel = self.item_tbl.selected()
        if sel is None:
            return
        it = self.items[int(sel)]

        def save(vals):
            q = vals["qty"]; p = dec_ok(vals["price"], Decimal(0))
            if not q.isdigit() or int(q) < 1:
                return "Quantity must be a whole number of at least 1."
            if p is None:
                return "Enter a valid unit price."
            it["qty"] = int(q); it["price"] = str(p); self.refresh_items(); return None
        form_dialog(self, it["name"], [("qty", "Quantity", str(it["qty"]), "entry", None), ("price", "Unit price for this invoice (saved product price is not changed)", it["price"], "entry", None)], save, 44)

    def remove_item(self):
        sel = self.item_tbl.selected()
        if sel is not None:
            del self.items[int(sel)]; self.refresh_items()

    def collect(self):
        v = {k: x.get().strip() for k, x in self.draft_vars.items()}
        if not self.items:
            raise ValueError("Add at least one product.")
        for it in self.items:
            if it["qty"] < 1:
                raise ValueError(f'Quantity must be at least 1 ({it["name"]}).')
            if dec_ok(it["price"], Decimal(0)) is None:
                raise ValueError(f'Enter a valid unit price for {it["name"]}.')
        if not v["name"]:
            raise ValueError("Customer name is required.")
        if not _valid_dt(v["dateTime"]):
            raise ValueError("Date & time must look like 05/09/2025 19:38.")
        if not (v["till"] and v["createdBy"] and v["pay"]):
            raise ValueError("Till no., created by and payment method cannot be empty.")
        if not v["txnId"]:
            raise ValueError("Transaction ID cannot be empty.")
        import re
        if not re.fullmatch(r"SOA\d{12}", v["orderNo"]):
            raise ValueError("Order number must be SOA followed by 12 digits.")
        return dict(storeName=v["storeName"], legal=v["legal"], sAddr1=v["sAddr1"], sAddr2=v["sAddr2"], sAddr3=v["sAddr3"], sPhone=v["sPhone"], gst=v["gst"],
                    till=v["till"], orderNo=v["orderNo"], createdBy=v["createdBy"], dateTime=v["dateTime"],
                    customer={k: v[k] for k in CUST_KEYS}, payMethod=v["pay"], last4=v["last4"], txnRef=v["txnRef"], transactionId=v["txnId"],
                    taxMode=self.repo.settings["taxMode"], cin=v["cin"], regd1=v["regd1"], regd2=v["regd2"], regd3=v["regd3"], site=v["site"], email=v["email_s"],
                    items=[dict(name=i["name"], type=i["type"], code=i["code"], hsn=i["hsn"], qty=i["qty"], unit=str(dec_ok(i["price"])), cgst=i["cgst"], sgst=i["sgst"]) for i in self.items])

    def preview_invoice(self):
        try:
            d = self.collect()
        except ValueError as e:
            messagebox.showwarning(APP_TITLE, str(e)); return
        tmp = os.path.join(self.repo.root, "_preview.pdf")
        pdf.write_pdf(d, tmp); self.show_pdf(tmp, d["orderNo"])

    def save_invoice(self):
        try:
            d = self.collect()
        except ValueError as e:
            messagebox.showwarning(APP_TITLE, str(e)); return
        if any(i["orderNo"] == d["orderNo"] for i in self.repo.invoices):
            messagebox.showwarning(APP_TITLE, "That order number is already used – click 'New order number'."); return
        try:
            path = pdf.write_pdf(d, self.repo.pdf_path(d["orderNo"]))
            total = layout.compute(d["items"], d["taxMode"])["grand"]
            self.repo.invoices.append(dict(orderNo=d["orderNo"], createdAt=int(__import__("time").time() * 1000), dateTime=d["dateTime"], customer=d["customer"]["name"], total=format(total, "f"), data=d))
            self.repo.save()
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not save invoice: {e}"); return
        self.new_draft(); self.goto("history"); self.show_pdf(path, d["orderNo"])

    # ================= PDF preview window =================
    def show_pdf(self, path, order_no):
        try:
            import pymupdf
            doc = pymupdf.open(path)
        except Exception:
            open_external(path); return
        win = tk.Toplevel(self); win.title(f"Invoice {order_no}"); win.geometry("640x860"); win.transient(self)
        bar = ttk.Frame(win, padding=6); bar.pack(fill="x")
        sc = Scrollable(win); sc.pack(fill="both", expand=True)
        win.imgs = []
        for pg in doc:
            png = pg.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2)).tobytes("png")
            img = tk.PhotoImage(data=png); win.imgs.append(img)
            tk.Label(sc.inner, image=img, bd=1, relief="solid").pack(pady=6)
        doc.close()

        def save_copy():
            f = filedialog.asksaveasfilename(parent=win, defaultextension=".pdf", initialfile=f"{order_no}.pdf", filetypes=[("PDF", "*.pdf")])
            if f:
                import shutil
                shutil.copyfile(path, f); messagebox.showinfo(APP_TITLE, "PDF saved.", parent=win)
        ttk.Button(bar, text="Save a copy…", command=save_copy).pack(side="left", padx=4)
        ttk.Button(bar, text="Open in PDF viewer", command=lambda: open_external(path)).pack(side="left", padx=4)
        ttk.Button(bar, text="Print", command=lambda: open_external(path, True)).pack(side="left", padx=4)
        ttk.Button(bar, text="Close", command=win.destroy).pack(side="right", padx=4)

    # ================= Products =================
    def build_products(self):
        f = self.tabs["products"]
        top = ttk.Frame(f); top.pack(fill="x")
        self.p_q = tk.StringVar(); self.p_q.trace_add("write", lambda *_: self.refresh_products())
        ttk.Label(top, text="Search").pack(side="left"); ttk.Entry(top, textvariable=self.p_q, width=30).pack(side="left", padx=6)
        for t, c in (("＋ Add product", lambda: self.product_form(None)), ("Edit", self.edit_product), ("Delete", self.del_product)):
            ttk.Button(top, text=t, command=c).pack(side="left", padx=4)
        mid = ttk.Frame(f); mid.pack(fill="both", expand=True, pady=8)
        self.p_tbl = Table(mid, [("name", "Item"), ("type", "Type"), ("code", "Code"), ("hsn", "HSN"), ("price", "Unit price"), ("cgst", "CGST %"), ("sgst", "SGST %")], [320, 130, 80, 90, 100, 70, 70], 18)
        self.p_tbl.pack(side="left", fill="both", expand=True)
        self.p_tbl.tree.bind("<<TreeviewSelect>>", lambda e: self.show_product_image())
        side = ttk.LabelFrame(mid, text=" Image ", padding=6); side.pack(side="left", fill="y", padx=(8, 0))
        self.img_lbl = ttk.Label(side, text="(no image)", width=30, anchor="center"); self.img_lbl.pack()
        self._img_token = 0

    def refresh_products(self):
        q = self.p_q.get().lower()
        self.p_tbl.fill([(p["id"], (p["name"], p["type"], p["code"], (self.repo.type_of(p["type"]) or {}).get("hsn", "-"), layout.money(dec_ok(p["price"]) or 0), p["cgst"], p["sgst"]))
                         for p in self.repo.products if q in f'{p["name"]} {p["type"]} {p["code"]}'.lower()])

    def show_product_image(self):
        sel = self.p_tbl.selected(); self._img_token += 1; tok = self._img_token
        p = next((x for x in self.repo.products if x["id"] == sel), None)
        self.img_lbl.config(image="", text="(no image)")
        if not p or not p["image"]:
            return

        def work():
            try:
                from PIL import Image, ImageTk
                data = urllib.request.urlopen(urllib.request.Request(p["image"], headers={"User-Agent": "Mozilla/5.0"}), timeout=8).read()
                im = Image.open(io.BytesIO(data)); im.thumbnail((240, 240))
                self.after(0, lambda: self._set_image(tok, ImageTk.PhotoImage(im)))
            except Exception:
                self.after(0, lambda: tok == self._img_token and self.img_lbl.config(text="(image unavailable offline)"))
        self.img_lbl.config(text="loading…"); threading.Thread(target=work, daemon=True).start()

    def _set_image(self, tok, photo):
        if tok == self._img_token:
            self.img_lbl.image = photo; self.img_lbl.config(image=photo, text="")

    def edit_product(self):
        p = next((x for x in self.repo.products if x["id"] == self.p_tbl.selected()), None)
        if p:
            self.product_form(p)

    def del_product(self):
        p = next((x for x in self.repo.products if x["id"] == self.p_tbl.selected()), None)
        if p and messagebox.askyesno(APP_TITLE, f'Delete {p["name"]}? Saved invoices are not affected.'):
            self.repo.products.remove(p); self.repo.save(); self.refresh_products()

    def product_form(self, p):
        names = [t["name"] for t in self.repo.types]
        typ = p["type"] if p and p["type"] in names else names[0]
        t0 = self.repo.type_of(typ)

        def save(v):
            price = dec_ok(v["price"], Decimal(0)); c = dec_ok(v["cgst"], Decimal(0), Decimal(50)); s = dec_ok(v["sgst"], Decimal(0), Decimal(50))
            if not v["name"]:
                return "Enter the item name."
            if len(v["code"]) != 6 or not v["code"].isdigit():
                return "Product code must be 6 digits."
            if any(x is not p and x["code"] == v["code"] for x in self.repo.products):
                return "That product code is already used."
            if price is None:
                return "Enter a valid unit price."
            if c is None or s is None:
                return "CGST/SGST must be between 0 and 50."
            if v["image"] and not v["image"].lower().startswith(("http://", "https://")):
                return "Image link must start with http:// or https://"
            rec = dict(type=v["type"], name=v["name"], code=v["code"], price=str(price), cgst=str(c), sgst=str(s), image=v["image"])
            if p is None:
                self.repo.products.append(dict(id=self.repo.new_id(), **rec))
            else:
                p.update(rec)
            self.repo.save(); self.refresh_products(); return None
        win, vars_, w = form_dialog(self, "Add product" if p is None else "Edit product", [
            ("type", "Product type", typ, "combo", names), ("name", "Item description / name", p["name"] if p else "", "entry", None),
            ("code", "Product code (6 digits, auto-generated)", p["code"] if p else self.repo.new_product_code(), "entry", None),
            ("price", "Unit price (₹)", p["price"] if p else "", "entry", None), ("cgst", "CGST %", p["cgst"] if p else t0["cgst"], "entry", None),
            ("sgst", "SGST %", p["sgst"] if p else t0["sgst"], "entry", None), ("image", "Image URL (https://…, link only)", p["image"] if p else "", "entry", None)], save, 46)
        hsn = ttk.Label(w["type"].master, text=f'HSN code (from product type): {t0["hsn"]}', foreground="#52606D"); hsn.grid(row=1, column=1, padx=8, sticky="w")

        def on_type(_e=None):
            t = self.repo.type_of(vars_["type"].get()); hsn.config(text=f'HSN code (from product type): {t["hsn"]}')
            if p is None:
                vars_["cgst"].set(t["cgst"]); vars_["sgst"].set(t["sgst"])
        w["type"].bind("<<ComboboxSelected>>", on_type)

    # ================= Customers =================
    def build_customers(self):
        f = self.tabs["customers"]
        top = ttk.Frame(f); top.pack(fill="x")
        self.c_q = tk.StringVar(); self.c_q.trace_add("write", lambda *_: self.refresh_customers())
        ttk.Label(top, text="Search").pack(side="left"); ttk.Entry(top, textvariable=self.c_q, width=30).pack(side="left", padx=6)
        for t, c in (("＋ Add customer", lambda: self.customer_form(None)), ("Edit", self.edit_customer), ("Delete", self.del_customer)):
            ttk.Button(top, text=t, command=c).pack(side="left", padx=4)
        self.c_tbl = Table(f, [("name", "Name"), ("addr", "Address"), ("city", "City"), ("state", "State"), ("pin", "PIN"), ("phone", "Phone"), ("email", "Email")], [200, 280, 110, 110, 70, 110, 190], 20)
        self.c_tbl.pack(fill="both", expand=True, pady=8)

    def refresh_customers(self):
        q = self.c_q.get().lower()
        self.c_tbl.fill([(c["id"], (c["name"], ", ".join(x for x in (c["addr1"], c["addr2"]) if x), c["city"], c["state"], c["pin"], c["phone"], c["email"]))
                         for c in self.repo.customers if q in f'{c["name"]} {c["phone"]} {c["city"]}'.lower()])

    def edit_customer(self):
        c = next((x for x in self.repo.customers if x["id"] == self.c_tbl.selected()), None)
        if c:
            self.customer_form(c)

    def del_customer(self):
        c = next((x for x in self.repo.customers if x["id"] == self.c_tbl.selected()), None)
        if c and messagebox.askyesno(APP_TITLE, f'Delete {c["name"]}? Saved invoices are not affected.'):
            self.repo.customers.remove(c); self.repo.save(); self.refresh_customers()

    def customer_form(self, c):
        def save(v):
            ph = "".join(ch for ch in v["phone"] if ch.isdigit())
            if not v["name"]:
                return "Enter the customer name."
            if v["pin"] and (len(v["pin"]) != 6 or not v["pin"].isdigit()):
                return "PIN code must be 6 digits."
            if v["phone"] and not 7 <= len(ph) <= 15:
                return "Enter a valid phone number."
            if v["email"] and "@" not in v["email"]:
                return "Enter a valid email address."
            if c is None:
                self.repo.customers.append(dict(id=self.repo.new_id(), **v))
            else:
                c.update(v)
            self.repo.save(); self.refresh_customers(); return None
        form_dialog(self, "Add customer" if c is None else "Edit customer",
                    [(k, lab, (c or {}).get(k, ""), "combo_edit" if k == "state" else "entry", layout.STATE_NAMES if k == "state" else None) for k, lab in zip(CUST_KEYS, CUST_LABELS)], save)

    # ================= History =================
    def build_history(self):
        f = self.tabs["history"]
        top = ttk.Frame(f); top.pack(fill="x")
        self.h_q = tk.StringVar(); self.h_q.trace_add("write", lambda *_: self.refresh_history())
        ttk.Label(top, text="Search (customer, order number, date)").pack(side="left"); ttk.Entry(top, textvariable=self.h_q, width=30).pack(side="left", padx=6)
        for t, c in (("Preview / view", self.view_invoice), ("Save PDF copy…", self.export_invoice), ("Re-create (edit as new)", self.recreate_invoice), ("Delete", self.del_invoice)):
            ttk.Button(top, text=t, command=c).pack(side="left", padx=4)
        self.h_tbl = Table(f, [("order", "Order number"), ("cust", "Customer"), ("date", "Date & time"), ("total", "Total")], [220, 300, 150, 120], 22)
        self.h_tbl.pack(fill="both", expand=True, pady=8)
        self.h_tbl.tree.bind("<Double-1>", lambda e: self.view_invoice())

    def refresh_history(self):
        q = self.h_q.get().lower()
        rows = sorted(self.repo.invoices, key=lambda r: r.get("createdAt", 0), reverse=True)
        self.h_tbl.fill([(r["orderNo"], (r["orderNo"], r["customer"], r["dateTime"], inr(dec_ok(r["total"]) or 0))) for r in rows if q in f'{r["customer"]} {r["orderNo"]} {r["dateTime"]}'.lower()])

    def _sel_inv(self):
        return next((r for r in self.repo.invoices if r["orderNo"] == self.h_tbl.selected()), None)

    def _ensure_pdf(self, r):
        p = self.repo.pdf_path(r["orderNo"])
        if not os.path.exists(p):
            pdf.write_pdf(r["data"], p)  # rebuilt from the stored snapshot
        return p

    def view_invoice(self):
        r = self._sel_inv()
        if r:
            self.show_pdf(self._ensure_pdf(r), r["orderNo"])

    def export_invoice(self):
        r = self._sel_inv()
        if r:
            f = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f'{r["orderNo"]}.pdf', filetypes=[("PDF", "*.pdf")])
            if f:
                import shutil
                shutil.copyfile(self._ensure_pdf(r), f); messagebox.showinfo(APP_TITLE, "PDF saved.")

    def recreate_invoice(self):
        r = self._sel_inv()
        if r:
            self.load_draft(r["data"])

    def del_invoice(self):
        r = self._sel_inv()
        if r and messagebox.askyesno(APP_TITLE, f'Delete invoice {r["orderNo"]} and its PDF?'):
            self.repo.invoices.remove(r)
            try:
                os.remove(self.repo.pdf_path(r["orderNo"]))
            except OSError:
                pass
            self.repo.save(); self.refresh_history()

    # ================= Store settings =================
    def build_store(self):
        sc = Scrollable(self.tabs["store"]); sc.pack(fill="both", expand=True)
        body = sc.inner; self.s_vars = {k: tk.StringVar() for k in ("legal", "name", "addr1", "addr2", "addr3", "phone", "gst", "cin", "regd1", "regd2", "regd3", "site", "email", "till", "createdBy", "payment")}
        self.s_tax = tk.BooleanVar()
        box = ttk.LabelFrame(body, text=" Store details ", padding=8); box.pack(fill="x", padx=6, pady=6)
        spec = [("Store name – line 1", "legal"), ("Store name – line 2", "name"), ("Address line 1", "addr1"), ("Address line 2", "addr2"), ("Address line 3", "addr3"),
                ("Phone number (use / for a second number)", "phone"), ("GST number", "gst"), ("CIN number", "cin"), ("Regd. office line 1", "regd1"), ("Regd. office line 2", "regd2"),
                ("Regd. office line 3", "regd3"), ("Website / brand name (e.g. falah.com)", "site"), ("Support email (printed as Email:…)", "email")]
        for i, (lab, k) in enumerate(spec):
            labeled(box, (i // 3) * 2, i % 3, lab, self.s_vars[k], width=36)
        d = ttk.LabelFrame(body, text=" Invoice defaults ", padding=8); d.pack(fill="x", padx=6, pady=6)
        for i, (lab, k) in enumerate((("Default till number", "till"), ("Default 'Created by'", "createdBy"), ("Default payment method", "payment"))):
            labeled(d, 0, i, lab, self.s_vars[k], width=30)
        ttk.Checkbutton(d, text="Show tax amounts as rate × price (legacy system style) instead of extracting tax from the inclusive price", variable=self.s_tax).grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=10)
        ttk.Button(body, text="Save settings", style="Accent.TButton", command=self.save_store).pack(anchor="w", padx=10, pady=8, ipadx=10, ipady=4)
        self.load_store_vars()

    def load_store_vars(self):
        s, t = self.repo.store, self.repo.settings
        for k in ("legal", "name", "addr1", "addr2", "addr3", "phone", "gst", "cin", "regd1", "regd2", "regd3", "site", "email"):
            self.s_vars[k].set(s[k])
        self.s_vars["till"].set(t["till"]); self.s_vars["createdBy"].set(t["createdBy"]); self.s_vars["payment"].set(t["payment"]); self.s_tax.set(t["taxMode"] == "ORIGINAL")

    def save_store(self):
        v = {k: x.get().strip() for k, x in self.s_vars.items()}
        if not (v["name"] and v["till"] and v["createdBy"] and v["payment"]):
            messagebox.showwarning(APP_TITLE, "Store name (line 2), till, created by and payment cannot be empty."); return
        for k in ("legal", "name", "addr1", "addr2", "addr3", "phone", "gst", "cin", "regd1", "regd2", "regd3", "site", "email"):
            self.repo.store[k] = v[k]
        self.repo.settings = dict(till=v["till"], createdBy=v["createdBy"], payment=v["payment"], taxMode="ORIGINAL" if self.s_tax.get() else "INCLUSIVE")
        self.repo.save(); self.new_draft(); messagebox.showinfo(APP_TITLE, "Settings saved.")

    # ================= Product types =================
    def build_types(self):
        f = self.tabs["types"]
        ttk.Label(f, text="HSN code and GST are stored per product type. HSN cannot be edited on an invoice.", foreground="#52606D").pack(anchor="w")
        self.t_tbl = Table(f, [("name", "Product type"), ("hsn", "HSN"), ("cgst", "Default CGST %"), ("sgst", "Default SGST %")], [240, 140, 140, 140], 10)
        self.t_tbl.pack(fill="x", pady=8)
        ttk.Button(f, text="Edit selected", command=self.edit_type).pack(anchor="w")

    def refresh_types(self):
        self.t_tbl.fill([(t["name"], (t["name"], t["hsn"], t["cgst"], t["sgst"])) for t in self.repo.types])

    def edit_type(self):
        t = self.repo.type_of(self.t_tbl.selected() or "")
        if not t:
            return

        def save(v):
            if not v["hsn"] or dec_ok(v["cgst"], Decimal(0)) is None or dec_ok(v["sgst"], Decimal(0)) is None:
                return "Enter HSN, CGST and SGST."
            t.update(hsn=v["hsn"], cgst=v["cgst"], sgst=v["sgst"]); self.repo.save(); self.refresh_types(); return None
        form_dialog(self, f'Edit {t["name"]}', [("hsn", "HSN code", t["hsn"], "entry", None), ("cgst", "Default CGST %", t["cgst"], "entry", None), ("sgst", "Default SGST %", t["sgst"], "entry", None)], save)

    # ================= Backup & restore =================
    def build_backup(self):
        f = self.tabs["backup"]
        row = ttk.Frame(f); row.pack(anchor="w")
        for t, c in (("Export all data (JSON)…", self.export_json), ("Import data from JSON…", self.import_json), ("Create backup now", lambda: (self.repo.backup(), self.refresh_backup()))):
            ttk.Button(row, text=t, command=c).pack(side="left", padx=(0, 8), ipady=4)
        ttk.Label(f, text="Saved backups (in the StoreInvoiceData\\backups folder)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(16, 4))
        self.b_tbl = Table(f, [("file", "Backup file")], [600], 10); self.b_tbl.pack(fill="x")
        ttk.Button(f, text="Restore selected backup", command=self.restore_backup).pack(anchor="w", pady=8)

    def refresh_backup(self):
        self.b_tbl.fill([(b, (b,)) for b in self.repo.backups()])

    def export_json(self):
        f = filedialog.asksaveasfilename(defaultextension=".json", initialfile="store-invoice-backup.json", filetypes=[("JSON", "*.json")])
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(self.repo.to_json(), fh, indent=2, ensure_ascii=False)
            messagebox.showinfo(APP_TITLE, "Exported.")

    def _do_import(self, text, merge):
        err = self.repo.import_text(text, merge)
        if err:
            messagebox.showerror(APP_TITLE, err)
        else:
            self.load_store_vars(); self.new_draft(); self.refresh(); messagebox.showinfo(APP_TITLE, "Imported (merged)." if merge else "Imported (replaced).")

    def import_json(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not f:
            return
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        a = messagebox.askyesnocancel("Import data", "YES = Merge (adds what is missing, keeps everything you have)\nNO = Replace (swap all data for the file's data)\nCANCEL = do nothing\n\nA safety backup is made first either way.")
        if a is not None:
            self._do_import(text, merge=bool(a))

    def restore_backup(self):
        b = self.b_tbl.selected()
        if b and messagebox.askyesno(APP_TITLE, "Replace all current data with this backup? A safety backup of the current data is made first."):
            with open(os.path.join(self.repo.backup_dir, b), encoding="utf-8") as fh:
                self._do_import(fh.read(), merge=False)


def _valid_dt(s):
    from datetime import datetime
    try:
        datetime.strptime(s, "%d/%m/%Y %H:%M"); return True
    except ValueError:
        return False


if __name__ == "__main__":
    App().mainloop()
