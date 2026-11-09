@echo off
REM Ouvre la page web Safety Agent sur ce PC uniquement.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environnement .venv introuvable. Voir le README : python -m venv .venv puis pip install -r requirements.txt
  pause
  exit /b 1
)
echo Ouverture de la page web... Laissez cette fenetre ouverte. Fermez-la pour arreter.
".venv\Scripts\python.exe" -m safety_agent web
pause
