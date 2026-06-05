@echo off
cd /d D:\vscode\city-sentiment-pipeline
call venv\Scripts\activate
echo Running R01 - Fetch Reddit posts (n-2)...
if not exist logs mkdir logs
python src/r01_fetch_reddit.py >> logs\r01_%date:~10,4%%date:~4,2%%date:~7,2%.log 2>&1
echo R01 done.