# Store Invoice Generator - Windows portable

Same invoice engine as the Android app (the layout code is a line-for-line port and was verified to produce identical output).
One file, no installation: copy `StoreInvoiceGenerator.exe` anywhere (USB stick, Desktop) and run it.

## Get the .exe (GitHub Actions)
1. Push the *contents* of this folder to a GitHub repo (`.github`, `app.py`, `assets` ... at the top level).
2. Actions -> **Build Windows portable EXE** -> Run workflow.
3. Download the artifact `StoreInvoiceGenerator-portable-exe` and unzip it.
(Or on a Windows PC with Python: double-click `build.bat`.)

## Portable data
A folder `StoreInvoiceData` is created next to the exe: `data.json`, `invoices\` (PDFs named by order number) and `backups\`.
Move the exe together with that folder to move everything. Windows SmartScreen may warn about an unsigned exe the first time: More info -> Run anyway.

## Font
The PDF uses the real **Courier New**: first `CourierNew.ttf` placed next to the exe (optional), then `C:\Windows\Fonts\cour.ttf`
(present on every Windows PC), and only as a last resort the bundled Liberation Mono.

## Android <-> Windows
Export all data (JSON) in one app and import it in the other - the file format is identical.
