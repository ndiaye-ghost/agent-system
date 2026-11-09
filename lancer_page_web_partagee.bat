@echo off
REM Ouvre la page web Safety Agent et la rend accessible aux collegues du reseau.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environnement .venv introuvable. Voir le README.
  pause
  exit /b 1
)
echo.
echo Adresse a donner aux collegues : http://%COMPUTERNAME%:8501
echo Laissez cette fenetre ouverte. Fermez-la pour arreter le partage.
echo.
".venv\Scripts\python.exe" -m safety_agent web --partage
pause
