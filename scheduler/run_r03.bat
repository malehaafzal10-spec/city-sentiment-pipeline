@echo off
cd /d D:\vscode\city-sentiment-pipeline
call venv\Scripts\activate
if not exist logs mkdir logs

:: Compute n-2 date using PowerShell
for /f %%a in ('powershell -NoProfile -Command "(Get-Date).AddDays(-2).ToString(\"yyyyMMdd\")"') do set TARGET_DATE=%%a

echo Running R03 for date: %TARGET_DATE%
python src/r03_fetch_comments.py --date %TARGET_DATE% >> logs\r03_%TARGET_DATE%.log 2>&1
echo R03 done.