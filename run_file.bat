@echo off
title Tourist Spot Pipeline - Data Ingestion
echo ===================================================
echo Starting Tourist Spot Ingestion Pipeline...
echo ===================================================
echo.




:: 3. Run the Python script
echo.
echo Executing file...

python src/01_ingest.py

::python 03_scrape_relevant_articles.py
:: 4. Keep the window open so you can read the output logs
echo.
echo ===================================================
echo Execution finished.
echo ===================================================
