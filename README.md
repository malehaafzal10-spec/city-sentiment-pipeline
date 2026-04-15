# City Sentiment Monitoring Pipeline

## 📖 Project Overview

The **City Sentiment Monitoring Pipeline** is an MLOps project designed to analyze traveler sentiment across eight major European cities. By leveraging data from NewsAPI and Reddit, the pipeline processes, scores, and aggregates sentiment data to provide actionable insights. The project includes a modern dashboard for real-time monitoring, automated workflows for daily and historical data processing, and robust evaluation mechanisms to ensure model quality.

This project demonstrates the integration of data engineering, machine learning, and MLOps principles to build a scalable and maintainable system for sentiment analysis.

---

## 🛠️ Problem Statement

Travelers often rely on online reviews, news, and social media to make decisions about destinations. However, the sheer volume of unstructured data makes it challenging to extract meaningful insights. 

This project addresses the following challenges:
1. **Relevance Filtering**: Identifying travel-related content from noisy data sources.
2. **Sentiment Analysis**: Scoring sentiment accurately using VADER and validating it with LLMs.
3. **Drift Detection**: Monitoring changes in sentiment over time to detect anomalies.
4. **Scalability**: Automating the pipeline for daily and historical data processing.

---

## 💻 Tech Stack

### **Languages & Frameworks**
- **Python**: Core programming language.
- **Streamlit**: Interactive dashboard for visualization.
- **VADER Sentiment**: Rule-based sentiment analysis.
- **MongoDB**: NoSQL database for data storage.

### **Tools & Libraries**
- **Requests**: API integration with NewsAPI and Reddit.
- **Pandas**: Data manipulation and analysis.
- **dotenv**: Environment variable management.
- **Chart.js**: Visualization in reports.
- **Altair**: Data visualization in Streamlit.

### **MLOps & Automation**
- **Docker**: Containerization for consistent environments.
- **GitHub Actions**: CI/CD for automated pipeline execution.
- **MongoDB Atlas**: Cloud database for scalability.

---

## 📂 Project Structure

.
├── app.py                     # Streamlit dashboard
├── run_pipeline.py            # Orchestrator for pipeline steps
├── preprocess/                # Historical data processing scripts
│   ├── 02a_store_relevant_docs_historical.py
│   ├── 03_score_historical.py
│   ├── 04_create_features_historical.py
├── src/                       # Core pipeline scripts
│   ├── s02_store_relevant_docs.py
│   ├── s03_score.py
│   ├── s04_create_features.py
│   ├── 05_evaluate_vader.py
│   ├── 06_llm_judge.py
│   ├── 07_monitor.py
├── artifacts/                 # Inspectors for pipeline outputs
│   ├── a00_inspect_artifacts.py
│   ├── a01_inspect_raw_docs.py
│   ├── a02_inspect_proc_docs.py
│   ├── a03_inspect_score.py
│   ├── a04_inspect_relevant.py
├── .github/workflows/         # GitHub Actions workflows
├── Dockerfile                 # Docker configuration
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation

---

## 🤖 GitHub Actions / Automation

The pipeline includes CI/CD workflows for automation:
1. **Daily Runs**: Automatically processes new data every day.
2. **Weekly Runs**: Aggregates weekly metrics and generates reports.
3. **GitHub Pages**: Publishes the dashboard as a static site.

To enable automation:
- Add API keys as repository secrets under **Settings → Secrets → Actions**.
- Trigger workflows manually or schedule them via GitHub Actions.

---

## 📊 Artifacts

The pipeline generates the following artifacts:

1. **Raw Ingestion**: Unfiltered data from NewsAPI and Reddit.
2. **Processed Documents**: Cleaned and relevance-filtered data.
3. **Sentiment Scores**: VADER-scored sentiment data.
4. **Feature Aggregates**: Weekly city-level metrics (e.g., sentiment, crowding, cost).

Artifacts are stored in MongoDB for traceability and reproducibility.

---

## 📈 Evaluation and Monitoring

### **Evaluation**
- **VADER Sentiment Validation**: Sentiment scores are cross-validated with LLMs (e.g., Groq API) to ensure accuracy.
- **Human-in-the-Loop (HITL)**: Disagreements between VADER and LLM predictions are flagged for manual review to improve model performance.

### **Monitoring**
- **Drift Detection**: Alerts are triggered for significant sentiment drops, low data volume, or deviations from rolling averages.
- **Dashboard**: Real-time metrics for sentiment, mentions, and anomalies are displayed on the Streamlit dashboard for easy monitoring.

---

## 👩‍💻👨‍💻 Contributors

This project was developed as part of the **M6 Data Engineering and MLOps** course at Aalborg University. It showcases the integration of data engineering, machine learning, and MLOps principles to solve real-world problems.

Contributors:
- **Karolina Bohdan** 
- **Faraiba Farnan**
- **Maleha Afzal**
- **Cristian Smoilis**
