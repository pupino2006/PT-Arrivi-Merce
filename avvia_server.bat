@echo off
cd /d "C:\Users\L.Ripà\Documents\GitHub\PT-Arrivi-Merce"
if exist "C:\Users\L.Ripà\Documents\GitHub\PT-Arrivi-Merce\.venv\Scripts\activate.bat" call "C:\Users\L.Ripà\Documents\GitHub\PT-Arrivi-Merce\.venv\Scripts\activate.bat"
echo Server avviato su http://0.0.0.0:8000
echo Chiudi questa finestra per fermare il server.
"C:\Users\L.Ripà\Documents\GitHub\PT-Arrivi-Merce\.venv\Scripts\python.exe" "C:\Users\L.Ripà\Documents\GitHub\PT-Arrivi-Merce\main.py"
pause
