"""
r06_clean_data.py — Clean aggregated data and categorize aspects.

Rules:
1. Delete aspects containing specific words (partial match).
2. Delete aspects matching a specific list (exact match).
3. Filter only documents up to June 1st, 2026 (included).
4. Map remaining aspects to Macro Categories (saved as 'aspect_cleaned').

Usage:
    Test Mode (Generates CSV grouped by Macro Categories):
        python r06_clean_data.py --test
    
    Production Mode (Saves to MongoDB):
        python r06_clean_data.py
"""

import os
import re
import argparse
import pandas as pd
from collections import Counter
from pymongo import MongoClient
import json
from dotenv import load_dotenv

load_dotenv(override=True)

# ==========================================
# Configuration
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
SOURCE_COLLECTION = "reddit_aggregated"
TARGET_COLLECTION = "reddit_cleaned"

# ==========================================
# Cleaning Rules
# ==========================================
WORDS_TO_DELETE = [
    "overall experience", "planning", "itinerary", "destination", 
    "destinations", "border", "island", "islands", "immigration", 
    "comparison", "region", "regions", "regional"
]

EXACT_MATCHES_TO_DELETE = [
    "border crossing", "location", "destination recommendation", 
    "value for money", "car rental", "visa requirements", 
    "trip duration", "city overall", "destination choice", 
    "destination appeal", "neighborhoods", "airport experience", 
    "tourist destinations", "alternative destination","duration of stay",
    "best time to visit","travel time", "tourist season", "time management", 
    "pace of travel", "travel pace","travel experience", "overall impression", "travel duration",
    "length of stay", "rural areas", "tourism", "travel flexibility", "time allocation", 
    "seasonal travel recommendation", "general impression", "time to visit","seasonal timing",
    "seasonal experience", "packing", "seasonality", "season", "age of travelers", "geographical location", 
    "country selection","general information", "dress code", "preparation","age suitability",  
    "pace of life", "timing of visit",
]

 


# ==========================================
# Macro Categories Mapping
# ==========================================
MACRO_CATEGORIES = {
    "Public Transportation": [
        "transportation", "public transportation", "logistics", "train service", 
        "public transport", "train travel", "transportation options", "flight options", 
        "taxi service", "flight connections", "airport accessibility", "flight duration", 
        "ease of travel", "public transit", "airport transportation", "train journey", 
        "bus service", "flight experience", "navigation", "transport", "flight", 
        "taxi services", "flight connectivity", "travel route", "city accessibility", 
        "train station", "train experience", "local transportation", "travel convenience", 
        "ferry ride", "distance and accessibility", "flight availability", 
        "location/accessibility", "bus travel"
    ],
    "Driving": [
        "driving experience", "driving", "road conditions", "traffic", "parking", 
        "scenic route", "scenic routes", "driving route", "tourist traffic", "road trips", 
        "road safety", "traffic laws", "scooter rental", "traffic safety", "road trip route","road trip"
    ],
    "Accommodation": [
        "accommodation", "accommodation location", "accommodation duration", 
        "accommodation options", "hotel", "accommodation cost", "accommodation/stopping point", 
        "accommodation deals", "hotel service", "accommodation booking", 
        "accommodation pricing", "accommodation/location preference", "glamping"
    ],
    "Food & Dining": [
        "food", "restaurant", "restaurants", "food options", "dining", "street food", 
        "cuisine", "food scene", "food and drink", "market", "markets", "wine", 
        "restaurant prices", "local food", "cafe", "dining options", "bar", 
        "restaurant options", "wine tasting", "food prices", "food quality", 
        "food pricing", "local cuisine", "seafood", "local drink", "dining experience", 
        "coffee shops", "bar/nightlife", "convenience store food", "food and wine"
    ],
    "Attractions": [
        "attractions", "attraction", "museums", "history", "old town", "tourist attractions", 
        "architecture", "historical sites", "sightseeing", "museum", "tourist attraction", 
        "landmarks", "castle", "uniqueness", "temples", "historical site", "temples and shrines", 
        "ruins", "landmark", "local attractions", "archeological site", "sights", 
        "castles", "cathedral", "cenotes", "historic sites", "amusement park", "historic landmarks"
    ],
    "Activities": [
        "hiking", "shopping", "city exploration", "activities", "tour", "guided tours", 
        "tour options", "tour package", "diving", "tour guides", "events", "gorilla trekking", 
        "activity", "snorkeling", "things to do", "cycling", "boat trip", "boat tour", 
        "photography opportunities", "photography", "exploration", "adventure activities", 
        "backpacking", "tours", "walking tours", "walking", "trekking", "surfing", 
        "tourist activities", "group tours", "forest tours", "scuba diving", "daytrip options",
        "activity accessibility", "tourist activity","day trip", "day trips","relaxation","daytrip"
    ],
    "Nature": [
        "natural beauty", "scenic views", "scenery", "national park", "wildlife", 
        "scenic beauty", "nature", "outdoor activities", "natural attractions", "hiking trails", 
        "natural attraction", "natural scenery", "wildlife viewing", "lake", "landscapes", 
        "parks", "safari experience", "scenic drive", "views", "national parks", "beauty", 
        "landscape", "lake experience", "countryside", "general beauty", "lake scenery", 
        "natural wonder", "vineyards", "parks and gardens", "park", "cave", "gardens", 
        "rainforest", "hot springs", "onsen experience", "beaches", "beach", "beach quality", 
        "beach experience", "coastal areas", "surroundings","national park experience", 
        "beach conditions", "coastline", "beach towns", "coastal scenery", "waterfront","overall beauty",  
        "viewpoint","surroundings", "physical activity", "altitude"
    ],
    "Social": [
        "local people", "people", "local interaction", "social scene", "nightlife", 
        "local behavior", "social interaction", "lifestyle", "solo travel experience", "romantic getaway", "romance",
        "solo travel", 
        "family-friendliness"
    ],
    "Hospitality": [
        "hospitality", "local hospitality", "honesty of locals", "local attitude", 
        "local attitude towards tourism"
    ],
    "Culture": [
        "atmosphere", "culture", "city atmosphere", "city charm", "cultural experience", 
        "town atmosphere", "local culture", "city vibe", "local experience", "charm", 
        "local customs", "town charm", "town character", "culture and people", 
        "local atmosphere", "village charm", "social etiquette", "cultural sensitivity", 
        "cultural interaction", "historic significance", "local exploration", "village atmosphere"
    ],
    "Safety": [
        "safety", "health and safety", "scams", "safety and security", "racism and discrimination", 
        "safety/security", "natural disasters"
    ],
    "Crowd": [
        "crowds", "tourist crowds", "crowd", "crowd levels", "crowds and tourism", 
        "crowd management", "overtourism", "tourist areas"
    ],
    "Infrastructure": [
        "cleanliness", "infrastructure", "tourist infrastructure", "language barrier", 
        "language", "air quality", "tourism infrastructure", "tourist information", 
        "ticketing system", "tourist stops", "pollution", "communication", "bureaucracy", 
        "signage", "connectivity", "tourist traps", "tourist reception", "technology", 
        "national park regulations"
    ],
    "City Experience": [
        "city experience", "city visit", "city life", "city worth visiting", "city preference", 
        "cities", "neighborhood", "small towns", "city attractions", "city activities", 
        "city recommendation", "city appeal", "city attractiveness", "city size", 
        "city worthiness", "urban landscape", "city duration", "city character", "city beauty", 
        "old city center", "city break", "city visit duration", "cities and towns", 
        "towns and villages", "town attractiveness", "city enjoyability","weather", "climate", "tourist atmosphere", 
        "comfort"
    ],

    "Cost": [
        "cost", "affordability", "prices", "budget", "cost of living", "flight prices", 
        "currency exchange", "price", "exchange rate", "payment methods", "flight cost", 
        "tipping culture"
    ]
}

# Build the reverse lookup dictionary for fast O(1) matching
ASPECT_TO_MACRO = {}
for category, aspects in MACRO_CATEGORIES.items():
    for asp in aspects:
        ASPECT_TO_MACRO[asp.lower()] = category

# ==========================================
# Helpers
# ==========================================
def is_valid_aspect(aspect_name):
    if not aspect_name:
        return False
    aspect_lower = str(aspect_name).lower().strip()
    
    # Exact Match Deletion
    if aspect_lower in EXACT_MATCHES_TO_DELETE:
        return False
        
    # Partial Word Match Deletion
    for word in WORDS_TO_DELETE:
        if word in aspect_lower:
            return False
            
    return True

# ==========================================
# Main
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Clean and categorize aggregated aspect data.")
    parser.add_argument(
        "--test", 
        action="store_true", 
        help="Run in test mode: outputs a CSV of Macro Category frequencies."
    )
    parser.add_argument(
        "--end-date", 
        type=str, 
        default="20260601", 
        help="Include data up to this date (YYYYMMDD). Default is 20260601 (June 1st)."
    )
    args = parser.parse_args()

    print("=" * 60)
    print("DATA CLEANING: CATEGORIZATION & FILTERING")
    print(f"Mode:          {'TEST (CSV ONLY)' if args.test else 'PRODUCTION (DB INSERT & ARTIFACTS)'}")
    print(f"Target Date:   Up to {args.end_date} (included)")
    print("=" * 60)

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    print(f"Fetching data from '{SOURCE_COLLECTION}'...")
    cursor = db[SOURCE_COLLECTION].find({})
    
    cleaned_records = []
    category_counter = Counter()
    
    total_docs = 0
    filtered_out_docs = 0
    date_skipped_docs = 0

    for doc in cursor:
        total_docs += 1
        
        # 1. Date Filtering
        run_id = doc.get("run_id", "")
        match = re.search(r"run_(\d{8})", run_id)
        if match:
            doc_date = match.group(1)
            if doc_date > args.end_date:
                date_skipped_docs += 1
                continue
        
        # 2. Aspect Filtering & Categorization
        aspect = doc.get("aspect", "")
        if is_valid_aspect(aspect):
            aspect_lower = str(aspect).lower().strip()
            
            # Lookup the macro category or default to "not defined"
            aspect_cleaned = ASPECT_TO_MACRO.get(aspect_lower, "not defined")
            
            # Assign new variable
            doc["aspect_cleaned"] = aspect_cleaned
            doc.pop("_id", None)
            cleaned_records.append(doc)
            
            # Count the frequency of the new Macro Category
            category_counter[aspect_cleaned] += 1
        else:
            filtered_out_docs += 1

    print("\n--- Summary ---")
    print(f"Total documents processed: {total_docs}")
    print(f"Skipped (After June 1st):  {date_skipped_docs}")
    print(f"Deleted by Filters:        {filtered_out_docs}")
    print(f"Amount 'not defined':      {category_counter.get('not defined', 0)}")
    print(f"Retained (Valid):          {len(cleaned_records)}")
    
    if not cleaned_records:
        print("No records left after filtering. Exiting.")
        return

    # ==========================================
    # TEST MODE: Output to CSV
    # ==========================================
    if args.test:
        output_dir = "artifacts/reports"
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, "macro_categories_frequency.csv")
        
        # Convert counter to DataFrame ordered by frequency
        df_categories = pd.DataFrame(
            category_counter.most_common(), 
            columns=["aspect_cleaned (Macro Category)", "Total Mentions"]
        )
        
        df_categories.to_csv(csv_path, index=False)
        print("=" * 60)
        print(f"✅ TEST MODE COMPLETE")
        print(f"Saved category frequency to: {csv_path}")
        print(f"\nTop Categories:\n{df_categories.head(10).to_string(index=False)}")
        print("=" * 60)

    # ==========================================
    # PRODUCTION MODE: Save to DB & Generate Artifacts
    # ==========================================
    else:
        target_coll = db[TARGET_COLLECTION]
        
        target_coll.drop()
        print(f"\nCleared old '{TARGET_COLLECTION}' collection.")
        
        if cleaned_records:
            target_coll.insert_many(cleaned_records)
            print("=" * 60)
            print(f"✅ PRODUCTION MODE COMPLETE")
            print(f"Successfully inserted {len(cleaned_records)} records into '{TARGET_COLLECTION}'.")
            
            # --- Artifact Collection ---
            output_dir = "artifacts/reports"
            os.makedirs(output_dir, exist_ok=True)
            artifact_path = os.path.join(output_dir, "production_cleaning_summary.json")
            
            # Prepare the requested metrics
            metrics = {
                "total_docs_processed": total_docs,
                "total_amount_deleted_by_filters": filtered_out_docs,
                "amount_of_not_defined": category_counter.get("not defined", 0),
                "total_retained": len(cleaned_records),
                "date_limit_applied": args.end_date
            }
            
            # Save the JSON artifact
            with open(artifact_path, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=4)
                
            print(f"Saved artifact summary to: {artifact_path}")
            print("=" * 60)

if __name__ == "__main__":
    main()