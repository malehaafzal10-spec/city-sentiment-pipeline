"""
pipeline.py — Travel Sentiment Orchestrator
Executes the data pipeline steps sequentially.
"""

import subprocess
import sys
import os
import logging

# Configure pipeline-level logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ORCHESTRATOR — %(message)s"
)
log = logging.getLogger("pipeline")

# The directory where your scripts are located
SCRIPTS_DIR = "src"

# The ordered list of scripts to execute
# Note: 05_rollback_run.py is excluded because it's a manual utility, not a daily step
PIPELINE_STEPS = [
    "s01a_ingest_daily_news.py",
    "s02_store_relevant_docs.py",
    "s03_score.py",
    "s04_create_features.py",
    "s05_track_artifacts.py"
]

def run_script(script_name: str):
    """Runs a single python script and halts execution if it fails."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    # Check if the file actually exists before trying to run it
    if not os.path.exists(script_path):
        log.error(f"File not found: '{script_path}'. Make sure the file exists in the '{SCRIPTS_DIR}' folder.")
        sys.exit(1)

    log.info(f"🚀 Starting step: {script_name}...")
    
    try:
        # sys.executable ensures we use the exact same Python environment/venv
        subprocess.check_call([sys.executable, script_path])
        log.info(f"✅ Successfully finished: {script_name}\n")
    
    except subprocess.CalledProcessError as e:
        log.error(f"❌ PIPELINE FAILED at step: {script_name}")
        log.error(f"Error details: {e}")
        sys.exit(1)  # Stop the entire pipeline immediately

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("STARTING TRAVEL SENTIMENT PIPELINE")
    log.info("=" * 60)
    
    for step in PIPELINE_STEPS:
        run_script(step)
        
    log.info("=" * 60)
    log.info("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
    log.info("=" * 60)