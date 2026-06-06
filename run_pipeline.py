"""
pipeline.py — Travel Sentiment Orchestrator
Executes the data pipeline steps sequentially.
"""

import subprocess
import sys
import os
import logging
import argparse
from datetime import datetime, timezone

# Configure pipeline-level logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ORCHESTRATOR — %(message)s"
)
log = logging.getLogger("pipeline")

# The directory where your scripts are located
SCRIPTS_DIR = "src"

def run_script(script_name: str, args: list):
    """Runs a single python script with arguments and halts execution if it fails."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    # Check if the file actually exists before trying to run it
    if not os.path.exists(script_path):
        log.error(f"File not found: '{script_path}'. Make sure the file exists in the '{SCRIPTS_DIR}' folder.")
        sys.exit(1)

    # Combine the python executable, the script path, and any arguments
    command = [sys.executable, script_path] + args
    
    log.info(f"🚀 Starting step: {script_name} (Args: {' '.join(args)})")
    
    try:
        # sys.executable ensures we use the exact same Python environment/venv
        subprocess.check_call(command)
        log.info(f"✅ Successfully finished: {script_name}\n")
    
    except subprocess.CalledProcessError as e:
        log.error(f"❌ PIPELINE FAILED at step: {script_name}")
        log.error(f"Error details: {e}")
        sys.exit(1)  # Stop the entire pipeline immediately

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the daily Travel Sentiment Pipeline.")
    parser.add_argument("--date", type=str, help="Target date in YYYY-MM-DD. Defaults to today's date if omitted.")
    
    args_parsed = parser.parse_args()
    
    # If a date is provided, use it. Otherwise, generate today's date automatically.
    if args_parsed.date:
        target_date = args_parsed.date
    else:
        target_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    log.info("=" * 60)
    log.info(f"STARTING TRAVEL SENTIMENT PIPELINE FOR DATE: {target_date}")
    log.info("=" * 60)
    
    # --- PIPELINE STEPS ---
    
    # Step 1: Ingest Daily News
    run_script("s01a_ingest_daily_news.py", ["--date", target_date])
    
    # Step 2: Extract Tourist Alerts (Production mode: test=0)
    run_script("n02_get_alert.py", ["--date", target_date, "--test", "0"])
        
    log.info("=" * 60)
    log.info("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
    log.info("=" * 60)
