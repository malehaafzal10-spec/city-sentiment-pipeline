import pandas as pd

FILE_PATH = "HITL_vader/random_50_vader_scored_articles_labeled.csv"

df = pd.read_csv(FILE_PATH)

# Clean text (important)
df["vader_label"] = df["vader_label"].str.lower().str.strip()
df["human_label"] = df["human_label"].str.lower().str.strip()

# Drop rows without human labels
df = df[df["human_label"].notna()]

# Compute correctness
df["correct"] = (df["vader_label"] == df["human_label"]).astype(int)

# Accuracy
accuracy = df["correct"].mean()

print(f"\n✅ Accuracy: {accuracy:.2%}")
print(f"Total samples: {len(df)}")

# Confusion matrix
confusion = pd.crosstab(df["human_label"], df["vader_label"])
print("\nConfusion Matrix:")
print(confusion)