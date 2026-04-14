import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

# Load your labeled files
news = pd.read_csv(
    "human_in_the_loop/LLM/outputs/human_news_hitl_sample.csv",
    sep=";",
    engine="python",
    on_bad_lines="skip"
)

reddit = pd.read_csv(
    "human_in_the_loop/LLM/outputs/human_reddit_hitl_sample.csv",
    sep=";",
    engine="python",
    on_bad_lines="skip"
)

# Clean column names
news.columns = news.columns.str.strip()
reddit.columns = reddit.columns.str.strip()

# Combine both
df = pd.concat([news, reddit], ignore_index=True)
df.columns = df.columns.str.strip()

# Convert to numeric
df["predicted_label"] = pd.to_numeric(df["predicted_label"], errors="coerce")
df["human_label"] = pd.to_numeric(df["human_label"], errors="coerce")

# Drop rows without valid labels
df = df.dropna(subset=["human_label", "predicted_label"])

# Convert to int
df["predicted_label"] = df["predicted_label"].astype(int)
df["human_label"] = df["human_label"].astype(int)

# Accuracy
accuracy = accuracy_score(df["human_label"], df["predicted_label"])
print(f"\n✅ Accuracy: {accuracy:.2f}")

# Confusion matrix
print("\n📊 Confusion Matrix:")
print(confusion_matrix(df["human_label"], df["predicted_label"]))

# Full report
print("\n📈 Classification Report:")
print(classification_report(df["human_label"], df["predicted_label"]))

# Per source
print("\n--- Per Source ---")
for source in ["news", "reddit"]:
    subset = df[df["source"] == source]
    if len(subset) > 0:
        acc = accuracy_score(subset["human_label"], subset["predicted_label"])
        print(f"{source.upper()} accuracy: {acc:.2f}")