@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto :failed
)
if not exist ".venv\greenhome-ready.txt" (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
  echo ready> .venv\greenhome-ready.txt
)
.venv\Scripts\python.exe -m streamlit run app.py
goto :eof
:failed
echo Setup failed. Install Python 3.12, then see README.md for manual setup.
pause
