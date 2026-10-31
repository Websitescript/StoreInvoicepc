"""PDF writer. Uses the real Courier New (portable folder, then Windows Fonts) and falls back to the bundled Liberation Mono."""
import os
import sys
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
import layout


def res(*p):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *p)


def exe_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


_fonts = {}


def mono_name():
    """Courier New lookup order: CourierNew.ttf next to the program, C:\\Windows\\Fonts\\cour.ttf, bundled Liberation Mono."""
    if "mono" not in _fonts:
        wf = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "cour.ttf")
        cands = [os.path.join(exe_dir(), "CourierNew.ttf"), res("assets", "CourierNew.ttf"), wf, res("assets", "LiberationMono-Regular.ttf")]
        for c in cands:
            if os.path.exists(c):
                try:
                    pdfmetrics.registerFont(TTFont("InvMono", c)); _fonts["mono"] = "InvMono"; _fonts["monofile"] = c; break
                except Exception:
                    continue
        else:
            _fonts["mono"] = "Courier"; _fonts["monofile"] = "built-in Courier"
        pdfmetrics.registerFont(TTFont("InvSans", res("assets", "DejaVuSans.ttf")))
    return _fonts["mono"]


def write_pdf(data, path):
    mono = mono_name()
    pages = layout.build(data)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    c = canvas.Canvas(path, pagesize=(layout.PAGE_W, layout.PAGE_H))
    c.setTitle(data["orderNo"])
    H = layout.PAGE_H
    for cmds in pages:
        for cmd in cmds:
            if cmd[0] == "t":
                c.setFont(mono, layout.FONT); c.drawString(cmd[1], H - (cmd[2] + layout.ASCENT), cmd[3])
            elif cmd[0] == "c":
                c.setFont("InvSans", layout.FONT); c.drawCentredString(cmd[1], H - cmd[2], cmd[3])
            else:
                _, cx, y, u, h, bits = cmd
                x0 = cx - len(bits) * u / 2
                i = 0
                while i < len(bits):
                    if bits[i]:
                        j = i
                        while j < len(bits) and bits[j]:
                            j += 1
                        c.rect(x0 + i * u, H - y - h, (j - i) * u, h, stroke=0, fill=1); i = j
                    else:
                        i += 1
        c.showPage()
    c.save()
    return path
