@echo off
REM Local build (needs Python 3.10+ on Windows). Produces dist\StoreInvoiceGenerator.exe
python -m pip install -r requirements.txt
python -m PyInstaller --onefile --windowed --noconfirm --name StoreInvoiceGenerator --add-data "assets;assets" --collect-all pymupdf --hidden-import PIL.ImageTk app.py
echo.
echo Done: dist\StoreInvoiceGenerator.exe
pause
