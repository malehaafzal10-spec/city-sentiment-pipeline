"""
r07_generate_reports.py — Extract results, tables, and plots from cleaned data.

Outputs (Academic Formatting):
    - 7.1 Most Positively Perceived Macro Categories (CSV + PNG)
    - 7.2 Most Negatively Perceived Macro Categories (CSV + PNG)
    - 7.3 Country-Level Sentiment Analysis (CSV + PNG)
    - 7.4 City-Level Sentiment Analysis (CSV + PNG)
    - 7.5 Sentiment Heatmap: Macro Category vs. Top Countries (CSV + PNG)
    - 7.6 Mention Volume vs. Sentiment Score (PNG)
    - 7.7 Posts vs. Comments Sentiment Discrepancy (CSV + PNG)
    - 7.8 The "Controversy" Index / Standard Deviation (CSV)

Usage:
    python r07_generate_reports.py
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

# ==========================================
# Configuration
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION = "reddit_cleaned"
RESULTS_DIR = "results"

# Minimum mentions required to be included in the top/bottom lists
MIN_MENTIONS = 5  

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def save_plot(filename, fig=None):
    if fig:
        fig.tight_layout()
        fig.savefig(os.path.join(RESULTS_DIR, filename), dpi=300, bbox_inches='tight')
    else:
        plt.tight_layout()
        plt.savefig(os.path.join(RESULTS_DIR, filename), dpi=300, bbox_inches='tight')
    plt.close()

# ==========================================
# Academic Plotting Style Configuration
# ==========================================
def set_academic_style():
    sns.set_style("ticks")
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif", "serif"],
        "axes.edgecolor": "black",
        "axes.linewidth": 1.0,
        "xtick.color": "black",
        "ytick.color": "black",
        "text.color": "black",
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
        # Ensure text is editable in vector graphics if needed later
        "pdf.fonttype": 42,
        "ps.fonttype": 42
    })

def main():
    print("=" * 60)
    print("GENERATING RESULTS: ACADEMIC TABLES & PLOTS")
    print("=" * 60)

    # 1. Connect to DB and Load Data
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    print(f"Fetching data from '{COLLECTION}'...")
    cursor = db[COLLECTION].find({})
    df = pd.DataFrame(list(cursor))
    
    if df.empty:
        print("No data found! Please ensure 'reddit_cleaned' has data.")
        return

    # 2. Data Pre-Processing
    ensure_dir(RESULTS_DIR)
    
    # Force sentiment to numeric, drop invalid rows
    df['sentiment_score'] = pd.to_numeric(df['sentiment_score'], errors='coerce')
    df = df.dropna(subset=['sentiment_score'])
    
    # Standardize text formats
    if 'aspect_cleaned' in df.columns:
        df['aspect_cleaned'] = df['aspect_cleaned'].astype(str).str.title()
    else:
        print("❌ Error: 'aspect_cleaned' column not found. Did you run r06?")
        return
        
    if 'city' in df.columns:
        df['city'] = df['city'].astype(str).str.title()
    if 'country' in df.columns:
        df['country'] = df['country'].astype(str).str.title()

    df = df[df['aspect_cleaned'] != 'Not Defined']

    # Apply Academic Style
    set_academic_style()

    # ==========================================
    # 7.1 & 7.2: MACRO CATEGORY-LEVEL SENTIMENT
    # ==========================================
    print("Generating 7.1 & 7.2 (Macro Categories)...")
    category_stats = df.groupby('aspect_cleaned').agg(
        Average_Sentiment=('sentiment_score', 'mean'),
        Total_Mentions=('sentiment_score', 'count')
    ).reset_index()
    
    category_stats = category_stats[category_stats['Total_Mentions'] >= MIN_MENTIONS]

    # 7.1 Most Positive Macro Categories
    top_positive = category_stats.sort_values('Average_Sentiment', ascending=False).head(15)
    top_positive.to_csv(os.path.join(RESULTS_DIR, "7_1_top_positive_macro_categories.csv"), index=False)
    
    plt.figure(figsize=(8, 6))
    sns.barplot(data=top_positive, x='Average_Sentiment', y='aspect_cleaned', color='darkgray', edgecolor='black', linewidth=1)
    plt.title(f"Top Positively Perceived Tourism Categories (n $\geq$ {MIN_MENTIONS})", pad=15)
    plt.xlim(1, 5)
    plt.xlabel("Average Sentiment Score (1-5)")
    plt.ylabel("Macro Category")
    sns.despine()
    save_plot("7_1_top_positive_macro_categories.png")

    # 7.2 Most Negative Macro Categories
    top_negative = category_stats.sort_values('Average_Sentiment', ascending=True).head(15)
    top_negative.to_csv(os.path.join(RESULTS_DIR, "7_2_top_negative_macro_categories.csv"), index=False)
    
    plt.figure(figsize=(8, 6))
    sns.barplot(data=top_negative, x='Average_Sentiment', y='aspect_cleaned', color='lightgray', edgecolor='black', linewidth=1)
    plt.title(f"Top Negatively Perceived Tourism Categories (n $\geq$ {MIN_MENTIONS})", pad=15)
    plt.xlim(1, 5)
    plt.xlabel("Average Sentiment Score (1-5)")
    plt.ylabel("Macro Category")
    sns.despine()
    save_plot("7_2_top_negative_macro_categories.png")

    # ==========================================
    # 7.3: COUNTRY-LEVEL SENTIMENT
    # ==========================================
    print("Generating 7.3 (Countries)...")
    country_df = df[df['country'] != 'None'].dropna(subset=['country'])
    country_stats = country_df.groupby('country').agg(
        Average_Sentiment=('sentiment_score', 'mean'),
        Total_Mentions=('sentiment_score', 'count')
    ).reset_index()
    
    country_stats = country_stats[country_stats['Total_Mentions'] >= MIN_MENTIONS]
    country_stats = country_stats.sort_values('Average_Sentiment', ascending=False)
    country_stats.to_csv(os.path.join(RESULTS_DIR, "7_3_country_sentiment.csv"), index=False)

    plt.figure(figsize=(10, 8))
    sns.barplot(data=country_stats.head(20), x='Average_Sentiment', y='country', color='silver', edgecolor='black', linewidth=1)
    plt.title("Country-Level Sentiment Analysis (Top 20)", pad=15)
    plt.xlim(1, 5)
    plt.xlabel("Average Sentiment Score (1-5)")
    plt.ylabel("Country")
    sns.despine()
    save_plot("7_3_country_sentiment.png")

    # ==========================================
    # 7.4: CITY-LEVEL SENTIMENT
    # ==========================================
    print("Generating 7.4 (Cities)...")
    city_df = df[df['city'] != 'None'].dropna(subset=['city'])
    city_stats = city_df.groupby(['city', 'country']).agg(
        Average_Sentiment=('sentiment_score', 'mean'),
        Total_Mentions=('sentiment_score', 'count')
    ).reset_index()
    
    city_stats = city_stats[city_stats['Total_Mentions'] >= MIN_MENTIONS]
    city_stats = city_stats.sort_values('Average_Sentiment', ascending=False)
    city_stats['City_Label'] = city_stats['city'] + " (" + city_stats['country'] + ")"
    city_stats.drop(columns=['City_Label']).to_csv(os.path.join(RESULTS_DIR, "7_4_city_sentiment.csv"), index=False)

    # Plot Top Cities
    plt.figure(figsize=(10, 8))
    sns.barplot(data=city_stats.head(20), x='Average_Sentiment', y='City_Label', color='darkgray', edgecolor='black', linewidth=1)
    plt.title(f"Highest Rated Cities (n $\geq$ {MIN_MENTIONS})", pad=15)
    plt.xlim(1, 5)
    plt.xlabel("Average Sentiment Score (1-5)")
    plt.ylabel("City")
    sns.despine()
    save_plot("7_4_city_sentiment_top.png")

    # Plot Bottom Cities
    plt.figure(figsize=(10, 8))
    sns.barplot(data=city_stats.tail(20), x='Average_Sentiment', y='City_Label', color='lightgray', edgecolor='black', linewidth=1)
    plt.title(f"Lowest Rated Cities (n $\geq$ {MIN_MENTIONS})", pad=15)
    plt.xlim(1, 5)
    plt.xlabel("Average Sentiment Score (1-5)")
    plt.ylabel("City")
    sns.despine()
    save_plot("7_4_city_sentiment_bottom.png")

    # ==========================================
    # 7.5: SENTIMENT HEATMAP (Category vs Country)
    # ==========================================
    print("Generating 7.5 (Sentiment Heatmap)...")
    top_countries = country_stats.sort_values('Total_Mentions', ascending=False).head(15)['country']
    heatmap_df = df[df['country'].isin(top_countries)]
    
    pivot_table = heatmap_df.pivot_table(
        index='country', 
        columns='aspect_cleaned', 
        values='sentiment_score', 
        aggfunc='mean'
    )
    pivot_table.to_csv(os.path.join(RESULTS_DIR, "7_5_sentiment_heatmap.csv"))

    plt.figure(figsize=(12, 8))
    # Academic diverging palette (Blue/Red is standard, but RdBu_r is colorblind-friendly)
    sns.heatmap(pivot_table, annot=True, cmap="RdBu_r", center=3.0, fmt=".1f", 
                linewidths=.5, linecolor='black', cbar_kws={'label': 'Average Sentiment'})
    plt.title("Sentiment Heatmap: Macro Categories across Top 15 Countries", pad=15)
    plt.xlabel("Macro Category")
    plt.ylabel("Country")
    plt.xticks(rotation=45, ha='right')
    save_plot("7_5_sentiment_heatmap.png")

    # ==========================================
    # 7.6: MENTION VOLUME VS. SENTIMENT (Scatter Plot)
    # ==========================================
    print("Generating 7.6 (Volume vs. Sentiment Scatter Plot)...")
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=category_stats, x='Total_Mentions', y='Average_Sentiment', 
                    s=80, color="black", edgecolor="black", alpha=0.7)
    
    for line in range(0, category_stats.shape[0]):
        plt.text(
            category_stats['Total_Mentions'].iloc[line] + (category_stats['Total_Mentions'].max() * 0.01), 
            category_stats['Average_Sentiment'].iloc[line], 
            category_stats['aspect_cleaned'].iloc[line], 
            horizontalalignment='left', size=9, color='black'
        )
        
    plt.title("Impact Analysis: Mention Volume vs. Sentiment Score", pad=15)
    plt.xlabel("Total Mentions (Volume)")
    plt.ylabel("Average Sentiment Score (1-5)")
    plt.axhline(y=category_stats['Average_Sentiment'].mean(), color='black', linestyle='--', alpha=0.6, label="Overall Avg Sentiment")
    plt.legend(frameon=False)
    sns.despine()
    save_plot("7_6_volume_vs_sentiment.png")

    # ==========================================
    # 7.7: POSTS VS COMMENTS DISCREPANCY
    # ==========================================
    print("Generating 7.7 (Posts vs Comments Discrepancy)...")
    if 'type' in df.columns:
        discrepancy_df = df.pivot_table(
            index='aspect_cleaned', 
            columns='type', 
            values='sentiment_score', 
            aggfunc=['mean', 'count']
        ).reset_index()
        
        discrepancy_df.columns = ['_'.join(col).strip('_') for col in discrepancy_df.columns.values]
        
        if 'mean_post' in discrepancy_df.columns and 'mean_comment' in discrepancy_df.columns:
            discrepancy_df = discrepancy_df[
                (discrepancy_df['count_post'] >= 3) & (discrepancy_df['count_comment'] >= 3)
            ]
            
            discrepancy_df['Discrepancy'] = discrepancy_df['mean_comment'] - discrepancy_df['mean_post']
            discrepancy_df = discrepancy_df.sort_values('Discrepancy', ascending=False)
            
            discrepancy_df.to_csv(os.path.join(RESULTS_DIR, "7_7_posts_vs_comments_discrepancy.csv"), index=False)

            plt.figure(figsize=(10, 6))
            sns.barplot(
                data=discrepancy_df, 
                x='Discrepancy', 
                y='aspect_cleaned', 
                color='gray', 
                edgecolor='black', 
                linewidth=1
            )
            plt.title("Sentiment Discrepancy: Comments vs. Original Posts", pad=15)
            plt.xlabel("Sentiment Score Difference ($\Delta$)")
            plt.ylabel("Macro Category")
            plt.axvline(x=0, color='black', linestyle='-', linewidth=1.5)
            sns.despine()
            save_plot("7_7_posts_vs_comments_discrepancy.png")
    else:
        print("⚠️ 'type' column not found. Skipping 7.7.")

    # ==========================================
    # 7.8: THE "CONTROVERSY" INDEX (Standard Deviation)
    # ==========================================
    print("Generating 7.8 (Controversy Index)...")
    controversy_stats = df.groupby('aspect_cleaned').agg(
        Average_Sentiment=('sentiment_score', 'mean'),
        Sentiment_StdDev=('sentiment_score', 'std'),
        Total_Mentions=('sentiment_score', 'count')
    ).reset_index()
    
    controversy_stats = controversy_stats[controversy_stats['Total_Mentions'] >= 10]
    controversy_stats = controversy_stats.sort_values('Sentiment_StdDev', ascending=False)
    controversy_stats.to_csv(os.path.join(RESULTS_DIR, "7_8_controversy_index.csv"), index=False)

    print("=" * 60)
    print("✅ SUCCESS: All plots and tables updated to Academic Formatting and saved to 'results/'.")
    print("=" * 60)

if __name__ == "__main__":
    main()