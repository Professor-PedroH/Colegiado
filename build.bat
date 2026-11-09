@echo off
REM Gera o programa (pasta dist\ColegiadoDemandas). Requer Python 3.10+ instalado.
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --windowed --name ColegiadoDemandas --icon assets\icon.ico --add-data "assets;assets" --collect-data docx --collect-data openpyxl main.py
echo.
echo Pronto: dist\ColegiadoDemandas\ColegiadoDemandas.exe
echo Para criar o instalador, abra installer.iss no Inno Setup e clique em Compile.
pause
