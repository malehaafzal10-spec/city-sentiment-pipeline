"""
public_app.py — City Sentiment Explorer
Run: streamlit run public_app.py
"""

import os
import pandas as pd
import streamlit as st
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI  = os.getenv("MONGO_URI")
DB_NAME    = os.getenv("MONGO_DB_NAME", "travel_pipeline_db")
COLLECTION = "reddit_cleaned"

# Cities to exclude from display — common English words picked up by FlashText
BLOCKLIST = {
    "most", "nice", "tours", "reading", "bar", "like", "rest", "sale",
    "well", "can", "more", "her", "his", "our", "run", "new", "old",
    "best", "west", "east", "north", "south", "worth", "bath", "deal",
    "rich", "man", "chester", "hamilton", "richmond", "oxford", "cambridge",
    "york", "kent", "victoria", "hamilton", "george", "darwin"
}

ASPECT_ICONS = {
    "Accommodation":        "🏨",
    "Activities":           "🎯",
    "Attractions":          "🏛️",
    "City Experience":      "🌆",
    "Cost":                 "💰",
    "Crowd":                "👥",
    "Culture":              "🎭",
    "Driving":              "🚗",
    "Food & Dining":        "🍽️",
    "Hospitality":          "🤝",
    "Infrastructure":       "🏗️",
    "Nature":               "🌿",
    "Public Transportation":"🚌",
    "Safety":               "🛡️",
    "Social":               "💬",
}

CITY_IMAGES = {
    # Europe
    "Paris":           "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=600&h=300&fit=crop",
    "Rome":            "https://images.unsplash.com/photo-1552832230-c0197dd311b5?w=600&h=300&fit=crop",
    "Barcelona":       "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=600&h=300&fit=crop",
    "Lisbon":          "https://images.unsplash.com/photo-1548707309-dcebeab9ea9b?w=600&h=300&fit=crop",
    "Amsterdam":       "https://images.unsplash.com/photo-1534351590666-13e3e96b5017?w=600&h=300&fit=crop",
    "Prague":          "https://images.unsplash.com/photo-1592906209472-a36b1f3782ef?w=600&h=300&fit=crop",
    "Athens":          "https://images.unsplash.com/photo-1555993539-1732b0258235?w=600&h=300&fit=crop",
    "London":          "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=600&h=300&fit=crop",
    "Vienna":          "https://images.unsplash.com/photo-1516550893923-42d28e5677af?w=600&h=300&fit=crop",
    "Madrid":          "https://images.unsplash.com/photo-1539037116277-4db20889f2d4?w=600&h=300&fit=crop",
    "Berlin":          "https://images.unsplash.com/photo-1560969184-10fe8719e047?w=600&h=300&fit=crop",
    "Florence":        "https://images.unsplash.com/photo-1541370976299-4d24be63f9b0?w=600&h=300&fit=crop",
    "Venice":          "https://images.unsplash.com/photo-1523906834658-6e24ef2386f9?w=600&h=300&fit=crop",
    "Budapest":        "https://images.unsplash.com/photo-1551867633-194f125bddfa?w=600&h=300&fit=crop",
    "Copenhagen":      "https://images.unsplash.com/photo-1513622470522-26c3c8a854bc?w=600&h=300&fit=crop",
    "Stockholm":       "https://images.unsplash.com/photo-1509356843151-3e7d96241e11?w=600&h=300&fit=crop",
    "Dubrovnik":       "https://images.unsplash.com/photo-1555990793-da11153b4559?w=600&h=300&fit=crop",
    "Santorini":       "https://images.unsplash.com/photo-1570077188670-e3a8d69ac5ff?w=600&h=300&fit=crop",
    "Mykonos":         "https://images.unsplash.com/photo-1601581875039-e899893d520c?w=600&h=300&fit=crop",
    "Zurich":          "https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?w=600&h=300&fit=crop",
    "Geneva":          "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600&h=300&fit=crop",
    "Brussels":        "https://images.unsplash.com/photo-1608531617867-4f3fb0efcc54?w=600&h=300&fit=crop",
    "Milan":           "https://images.unsplash.com/photo-1512850183-6d7990f42385?w=600&h=300&fit=crop",
    "Naples":          "https://images.unsplash.com/photo-1547981609-4b6bfe67ca0b?w=600&h=300&fit=crop",
    "Porto":           "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=600&h=300&fit=crop",
    "Seville":         "https://images.unsplash.com/photo-1559181567-c3190ca9be46?w=600&h=300&fit=crop",
    "Krakow":          "https://images.unsplash.com/photo-1584466977773-e625c37cdd50?w=600&h=300&fit=crop",
    "Warsaw":          "https://images.unsplash.com/photo-1607427293702-036933bbf746?w=600&h=300&fit=crop",
    "Oslo":            "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?w=600&h=300&fit=crop",
    "Helsinki":        "https://images.unsplash.com/photo-1538332576228-eb5b4c4de6f5?w=600&h=300&fit=crop",
    "Reykjavik":       "https://images.unsplash.com/photo-1476610182048-b716b8518aae?w=600&h=300&fit=crop",
    "Edinburgh":       "https://images.unsplash.com/photo-1539037116277-4db20889f2d4?w=600&h=300&fit=crop",
    "Dublin":          "https://images.unsplash.com/photo-1549918864-48ac978761a4?w=600&h=300&fit=crop",
    "Bruges":          "https://images.unsplash.com/photo-1491557345352-5929e343eb89?w=600&h=300&fit=crop",
    "Valletta":        "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=600&h=300&fit=crop",
    "Tallinn":         "https://images.unsplash.com/photo-1565008447742-97f6f38c985c?w=600&h=300&fit=crop",
    "Riga":            "https://images.unsplash.com/photo-1567604130959-e674be75aacd?w=600&h=300&fit=crop",
    "Vilnius":         "https://images.unsplash.com/photo-1565008447742-97f6f38c985c?w=600&h=300&fit=crop",
    "Sarajevo":        "https://images.unsplash.com/photo-1568395260838-f6bbe4f62f97?w=600&h=300&fit=crop",
    "Ljubljana":       "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=600&h=300&fit=crop",
    "Kotor":           "https://images.unsplash.com/photo-1555990793-da11153b4559?w=600&h=300&fit=crop",
    "Tbilisi":         "https://images.unsplash.com/photo-1567008257516-8a2e5bf8b7d5?w=600&h=300&fit=crop",
    # Asia
    "Tokyo":           "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=600&h=300&fit=crop",
    "Kyoto":           "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=600&h=300&fit=crop",
    "Osaka":           "https://images.unsplash.com/photo-1590559899731-a382839e5549?w=600&h=300&fit=crop",
    "Bangkok":         "https://images.unsplash.com/photo-1508009603885-50cf7c579365?w=600&h=300&fit=crop",
    "Singapore":       "https://images.unsplash.com/photo-1525625293386-3f8f99389edd?w=600&h=300&fit=crop",
    "Bali":            "https://images.unsplash.com/photo-1537996194471-e657df975ab4?w=600&h=300&fit=crop",
    "Istanbul":        "https://images.unsplash.com/photo-1524231757912-21f4fe3a7200?w=600&h=300&fit=crop",
    "Dubai":           "https://images.unsplash.com/photo-1512453979798-5ea266f8880c?w=600&h=300&fit=crop",
    "Hong Kong":       "https://images.unsplash.com/photo-1536599018102-9f803c140fc1?w=600&h=300&fit=crop",
    "Seoul":           "https://images.unsplash.com/photo-1517154421773-0529f29ea451?w=600&h=300&fit=crop",
    "Hanoi":           "https://images.unsplash.com/photo-1509030450996-dd1a26dda07a?w=600&h=300&fit=crop",
    "Ho Chi Minh City":"https://images.unsplash.com/photo-1583417319070-4a69db38a482?w=600&h=300&fit=crop",
    "Hoi An":          "https://images.unsplash.com/photo-1559592413-7cec4d0cae2b?w=600&h=300&fit=crop",
    "Chiang Mai":      "https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=600&h=300&fit=crop",
    "Phuket":          "https://images.unsplash.com/photo-1589394815804-964ed0be2eb5?w=600&h=300&fit=crop",
    "Kathmandu":       "https://images.unsplash.com/photo-1507743617593-0a422c9bb7f5?w=600&h=300&fit=crop",
    "Colombo":         "https://images.unsplash.com/photo-1564501049412-61c2a3083791?w=600&h=300&fit=crop",
    "Taipei":          "https://images.unsplash.com/photo-1470004914212-05527e49370b?w=600&h=300&fit=crop",
    "Kuala Lumpur":    "https://images.unsplash.com/photo-1596422846543-75c6fc197f07?w=600&h=300&fit=crop",
    "Jakarta":         "https://images.unsplash.com/photo-1555899434-94d1368aa7af?w=600&h=300&fit=crop",
    "Mumbai":          "https://images.unsplash.com/photo-1562979314-bee7453e911c?w=600&h=300&fit=crop",
    "Delhi":           "https://images.unsplash.com/photo-1587474260584-136574528ed5?w=600&h=300&fit=crop",
    "Jaipur":          "https://images.unsplash.com/photo-1477587458883-47145ed6a225?w=600&h=300&fit=crop",
    "Udaipur":         "https://images.unsplash.com/photo-1477587458883-47145ed6a225?w=600&h=300&fit=crop",
    "Goa":             "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?w=600&h=300&fit=crop",
    # Americas
    "New York":        "https://images.unsplash.com/photo-1522083165195-3424ed129620?w=600&h=300&fit=crop",
    "Los Angeles":     "https://images.unsplash.com/photo-1534190760961-74e8c1c5c3da?w=600&h=300&fit=crop",
    "San Francisco":   "https://images.unsplash.com/photo-1501594907352-04cda38ebc29?w=600&h=300&fit=crop",
    "Chicago":         "https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=600&h=300&fit=crop",
    "Miami":           "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600&h=300&fit=crop",
    "New Orleans":     "https://images.unsplash.com/photo-1568091105571-b9a5c4f8f4dd?w=600&h=300&fit=crop",
    "Toronto":         "https://images.unsplash.com/photo-1517090504586-fde19ea6066f?w=600&h=300&fit=crop",
    "Vancouver":       "https://images.unsplash.com/photo-1559511260-66a654ae982a?w=600&h=300&fit=crop",
    "Montreal":        "https://images.unsplash.com/photo-1519178614-68673b201f36?w=600&h=300&fit=crop",
    "Mexico City":     "https://images.unsplash.com/photo-1518105779142-d975f22f1b0a?w=600&h=300&fit=crop",
    "Buenos Aires":    "https://images.unsplash.com/photo-1589909202802-8f4aadce1849?w=600&h=300&fit=crop",
    "Rio de Janeiro":  "https://images.unsplash.com/photo-1483729558449-99ef09a8c325?w=600&h=300&fit=crop",
    "Cusco":           "https://images.unsplash.com/photo-1587595431973-160d0d94add1?w=600&h=300&fit=crop",
    "Cartagena":       "https://images.unsplash.com/photo-1583997052103-b4a1cb974ce5?w=600&h=300&fit=crop",
    # Africa & Middle East
    "Marrakech":       "https://images.unsplash.com/photo-1548013146-72479768bada?w=600&h=300&fit=crop",
    "Cairo":           "https://images.unsplash.com/photo-1572252009286-268acec5ca0a?w=600&h=300&fit=crop",
    "Cape Town":       "https://images.unsplash.com/photo-1580060839134-75a5edca2e99?w=600&h=300&fit=crop",
    "Nairobi":         "https://images.unsplash.com/photo-1611348586804-61bf6c080437?w=600&h=300&fit=crop",
    "Zanzibar":        "https://images.unsplash.com/photo-1586861203927-800a5acdcc4d?w=600&h=300&fit=crop",
    "Tel Aviv":        "https://images.unsplash.com/photo-1544639561-6f8d9b9b8f75?w=600&h=300&fit=crop",
    "Petra":           "https://images.unsplash.com/photo-1569383746724-6f1b882b8f46?w=600&h=300&fit=crop",
    # Oceania
    "Sydney":          "https://images.unsplash.com/photo-1506973035872-a4ec16b8e8d9?w=600&h=300&fit=crop",
    "Melbourne":       "https://images.unsplash.com/photo-1514395462725-fb4566210144?w=600&h=300&fit=crop",
    "Auckland":        "https://images.unsplash.com/photo-1507699622108-4be3abd695ad?w=600&h=300&fit=crop",
    "Queenstown":      "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600&h=300&fit=crop",
}
DEFAULT_IMG = "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=600&h=300&fit=crop"

@st.cache_data(ttl=86400)
def get_img(city):
    if city in CITY_IMAGES:
        return CITY_IMAGES[city]
    # Try Wikipedia API for city image
    try:
        import urllib.request, json, urllib.parse
        query = urllib.parse.quote(city)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "CityApp/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
            img = data.get("thumbnail", {}).get("source", "")
            if img:
                # Get larger version
                img = img.replace("/200px-", "/600px-").replace("/320px-", "/600px-")
                return img
    except:
        pass
    return DEFAULT_IMG

st.set_page_config(page_title="Where to next?", page_icon="✈️", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@800,700,500,400&f[]=satoshi@700,500,400,300&display=swap');

:root {
    --bg:     #f5f4f0;
    --card:   #ffffff;
    --border: #e5e2d9;
    --text:   #161410;
    --text2:  #52504a;
    --text3:  #a09c93;
    --green:  #1d7a52;
    --gbg:    #eaf5ee;
    --amber:  #b45309;
    --abg:    #fef3c7;
    --red:    #c0392b;
    --rbg:    #fdecea;
    --blue:   #1e4fa3;
    --bbg:    #eef2fc;
}

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"], .stApp { background: var(--bg) !important; font-family: 'Satoshi', sans-serif !important; color: var(--text) !important; }

/* Remove ALL streamlit default padding */
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stAppViewContainer"] { padding: 0 !important; }

/* Constrained content width */
.page-wrap { max-width: 1200px; margin: 0 auto; padding: 2.5rem 2rem 4rem; }

/* Hero — full width */
.hero { background: linear-gradient(135deg, #1a3d2b 0%, #0f2318 60%, #0a1f14 100%); padding: 3rem 0; }
.hero-inner { max-width: 1200px; margin: 0 auto; padding: 0 2rem; position: relative; }
.hero::before { content:''; position:absolute; inset:0; }

/* Selectbox — single clean one */
div[data-testid="stSelectbox"] label { display: none !important; }
div[data-testid="stSelectbox"] > div > div {
    background: white !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 10px !important;
    font-size: 0.88rem !important;
    font-family: 'Satoshi', sans-serif !important;
    color: #161410 !important;
    padding: 0.55rem 0.9rem !important;
}
div[data-testid="stSelectbox"] span,
div[data-testid="stSelectbox"] div[class*="singleValue"],
div[data-testid="stSelectbox"] div[class*="placeholder"] {
    color: #161410 !important;
}

/* Force equal height city cards */
[data-testid="column"] > div > div > div > div {
    height: 100%;
}
div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
    height: 100%;
}

/* Sort selectbox — smaller */
.sort-box div[data-testid="stSelectbox"] > div > div {
    font-size: 0.78rem !important;
    padding: 0.38rem 0.8rem !important;
    border-radius: 8px !important;
    background: white !important;
}

/* Buttons */
.stButton > button {
    font-family: 'Satoshi', sans-serif !important;
    font-size: 0.76rem !important;
    font-weight: 600 !important;
    background: var(--text) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.42rem 1rem !important;
    width: 100% !important;
    transition: opacity 0.15s !important;
    letter-spacing: 0.01em !important;
}
.stButton > button:hover { opacity: 0.8 !important; }
.back-btn .stButton > button {
    background: white !important; color: var(--text2) !important;
    border: 1.5px solid var(--border) !important; width: auto !important;
}

#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none !important; }
div[data-testid="stDecoration"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


# ── DATA ──────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return client[DB_NAME]

@st.cache_data(ttl=300)
def load_data():
    db = get_db()
    docs = list(db[COLLECTION].find(
        {"sentiment_score": {"$exists": True, "$type": "number"},
         "aspect_cleaned": {"$nin": ["not defined", None]}},
        {"city": 1, "country": 1, "aspect_cleaned": 1, "sentiment_score": 1}
    ))
    df = pd.DataFrame(docs)
    if df.empty: return df
    df = df.dropna(subset=["sentiment_score", "city"])
    df["sentiment_score"] = pd.to_numeric(df["sentiment_score"], errors="coerce")
    df = df.dropna(subset=["sentiment_score"])
    df["city"]    = df["city"].str.strip()
    df["country"] = df["country"].fillna("").str.strip()
    df = df[~df["city"].str.lower().isin(BLOCKLIST)]
    return df

def get_top10(df, sort_aspect="Overall"):
    if df.empty: return pd.DataFrame()
    if sort_aspect == "Overall":
        agg = df.groupby(["city","country"]).agg(
            avg=("sentiment_score","mean"), n=("sentiment_score","count")
        ).reset_index()
    else:
        sub = df[df["aspect_cleaned"] == sort_aspect]
        if sub.empty: return pd.DataFrame()
        agg = sub.groupby(["city","country"]).agg(
            avg=("sentiment_score","mean"), n=("sentiment_score","count")
        ).reset_index()
    agg = agg[agg["n"] >= 3].sort_values("avg", ascending=False).head(10).reset_index(drop=True)
    agg["avg"] = agg["avg"].round(2)
    return agg

def score_cls(s):
    if s >= 4.0: return "green"
    if s >= 3.0: return "amber"
    return "red"

def score_lbl(s):
    if s >= 4.2: return "Excellent"
    if s >= 3.8: return "Very Good"
    if s >= 3.3: return "Good"
    if s >= 2.8: return "Mixed"
    return "Poor"

def bar_pct(s): return max(0, min(100, (s - 1) / 4 * 100))
def bar_col(s):
    if s >= 4.0: return "#1d7a52"
    if s >= 3.0: return "#b45309"
    return "#c0392b"

color_map = {"green":"#1d7a52","amber":"#b45309","red":"#c0392b"}
bg_map    = {"green":"#eaf5ee","amber":"#fef3c7","red":"#fdecea"}

# ── SESSION ───────────────────────────────────────────────────────────────────
for k, v in [("view","home"),("city",None),("ctype","city"),("search_counter",0)]:
    if k not in st.session_state: st.session_state[k] = v

try:
    df = load_data()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

n_cities = df["city"].nunique() if not df.empty else 0
n_ctries = df["country"].nunique() if not df.empty else 0
n_scores = len(df)

# ══════════════════════════════════════════════════════════════════════════════
# HERO — full width
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="hero">
  <div class="hero-inner">
    <div style="position:absolute;inset:0;background:radial-gradient(ellipse at 75% 40%, rgba(74,180,120,0.12) 0%,transparent 55%),radial-gradient(ellipse at 20% 80%, rgba(29,122,82,0.1) 0%,transparent 50%);pointer-events:none;"></div>
    <div style="position:relative;">
      <div style="font-size:0.6rem;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;color:#c9a84c;margin-bottom:0.8rem;">✈ Traveller Intelligence</div>
      <div style="font-size:clamp(1.8rem,3.5vw,3rem);font-weight:800;color:#fff;line-height:1.05;letter-spacing:-0.03em;margin-bottom:0.8rem;">
        Where should you go <span style="color:#c9a84c;">next?</span>
      </div>
      <div style="font-size:0.85rem;color:rgba(255,255,255,0.4);max-width:440px;line-height:1.65;margin-bottom:2rem;">
        Real traveller sentiment from Reddit — analysed daily across thousands of destinations.
      </div>
      <div style="display:flex;gap:2.5rem;">
        <div><div style="font-size:1.4rem;font-weight:800;color:#fff;">{n_cities:,}</div><div style="font-size:0.58rem;color:rgba(255,255,255,0.28);letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">Cities</div></div>
        <div><div style="font-size:1.4rem;font-weight:800;color:#fff;">{n_ctries:,}</div><div style="font-size:0.58rem;color:rgba(255,255,255,0.28);letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">Countries</div></div>
        <div><div style="font-size:1.4rem;font-weight:800;color:#fff;">{n_scores:,}</div><div style="font-size:0.58rem;color:rgba(255,255,255,0.28);letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">Aspect ratings</div></div>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── PAGE WRAP ─────────────────────────────────────────────────────────────────
_, main_col, _ = st.columns([1, 10, 1])

with main_col:

    st.markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)

    # ── SEARCH — single selectbox, no extra label div ──────────────────────
    cities_list  = sorted(df["city"].dropna().unique().tolist()) if not df.empty else []
    country_list = sorted(df["country"].dropna().unique().tolist()) if not df.empty else []
    opts = [""] + [f"🏙  {c}" for c in cities_list] + [f"🌍  {c}" for c in country_list]

    st.markdown('<p style="font-size:0.7rem;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#a09c93;margin-bottom:0.4rem;">🔍 Search a destination</p>', unsafe_allow_html=True)

    sel = st.selectbox("search", opts,
        format_func=lambda x: "Type a city or country..." if x == "" else x,
        label_visibility="collapsed", key=f"search_{st.session_state.search_counter}")
    
    st.markdown("<div style='margin-bottom:1.5rem'></div>", unsafe_allow_html=True)

    if sel:
        name  = sel[3:].strip()
        ctype = "country" if sel.startswith("🌍") else "city"
        st.session_state.update({"view":"detail","city":name,"ctype":ctype})

    # ══════════════════════════════════════════════════════════════════════════
    # DETAIL VIEW
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.view == "detail" and st.session_state.city:
        name  = st.session_state.city
        ctype = st.session_state.ctype

        st.markdown('<div class="back-btn">', unsafe_allow_html=True)
        if st.button("← Back to Top 10", key="back"):
            st.session_state.update({"view":"home","city":None,"search_counter": st.session_state.search_counter + 1})
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

        sub = df[df["city"].str.lower() == name.lower()] if ctype == "city" else df[df["country"].str.lower() == name.lower()]

        if sub.empty:
            st.warning(f"No data found for **{name}**.")
        else:
            overall  = sub["sentiment_score"].mean()
            total_m  = len(sub)
            country_ = sub["country"].mode()[0] if ctype == "city" else name
            sc       = score_cls(overall)
            lbl      = score_lbl(overall)
            img      = get_img(name)
            col_     = color_map[sc]
            bg_      = bg_map[sc]
            p        = bar_pct(overall)

            hc1, hc2 = st.columns([3, 1])
            with hc1:
                st.markdown(f"""
                <div style="background:white;border:1.5px solid #e5e2d9;border-radius:16px;overflow:hidden;margin-bottom:1.2rem;">
                  <img src="{img}" style="width:100%;height:200px;object-fit:cover;display:block;">
                  <div style="padding:1.5rem 1.7rem;">
                    <div style="font-size:1.8rem;font-weight:800;color:#161410;letter-spacing:-0.03em;line-height:1.1;">{name}</div>
                    <div style="font-size:0.78rem;color:#a09c93;margin:0.2rem 0 0.9rem;">{country_}</div>
                    <div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:0.4rem;">
                      <span style="font-size:2.3rem;font-weight:800;color:{col_};letter-spacing:-0.04em;line-height:1;">{overall:.1f}</span>
                      <span style="font-size:0.8rem;color:#a09c93;">/ 5.0</span>
                      <span style="background:{bg_};color:{col_};font-size:0.65rem;font-weight:700;padding:0.2rem 0.65rem;border-radius:20px;">{lbl}</span>
                    </div>
                    <div style="font-size:0.7rem;color:#a09c93;">{total_m:,} aspect ratings · {sub["aspect_cleaned"].nunique()} categories</div>
                  </div>
                </div>""", unsafe_allow_html=True)

            with hc2:
                st.markdown(f"""
                <div style="background:white;border:1.5px solid #e5e2d9;border-radius:16px;padding:1.5rem;height:100%;">
                  <div style="font-size:0.58rem;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:#a09c93;margin-bottom:0.9rem;">Overall Score</div>
                  <div style="font-size:2.8rem;font-weight:800;color:{col_};letter-spacing:-0.04em;line-height:1;">{overall:.1f}</div>
                  <div style="font-size:0.7rem;color:#a09c93;margin-bottom:0.9rem;">out of 5.0</div>
                  <div style="height:7px;background:#f0ede5;border-radius:7px;overflow:hidden;margin-bottom:1.2rem;">
                    <div style="width:{p:.0f}%;height:100%;background:{col_};border-radius:7px;"></div>
                  </div>
                  <div style="font-size:0.7rem;color:#52504a;line-height:2;">
                    <div>📊 {total_m:,} data points</div>
                    <div>🏷️ {sub["aspect_cleaned"].nunique()} aspects</div>
                    <div>📍 {sub["city"].nunique()} {"city" if sub["city"].nunique()==1 else "cities"}</div>
                  </div>
                </div>""", unsafe_allow_html=True)

            st.markdown("""
            <div style="display:flex;align-items:baseline;gap:0.7rem;margin:1.6rem 0 1.1rem;">
              <span style="font-size:1rem;font-weight:800;color:#161410;letter-spacing:-0.02em;">Aspect Breakdown</span>
              <span style="background:#eef2fc;color:#1e4fa3;font-size:0.58rem;font-weight:700;padding:0.18rem 0.6rem;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;">What travellers say</span>
            </div>""", unsafe_allow_html=True)

            asp_agg = sub.groupby("aspect_cleaned").agg(
                avg=("sentiment_score","mean"), n=("sentiment_score","count")
            ).reset_index().sort_values("avg", ascending=False)

            asp_cols = st.columns(4)
            for i, (_, r) in enumerate(asp_agg.iterrows()):
                asp  = r["aspect_cleaned"]
                avg  = r["avg"]
                cnt  = int(r["n"])
                ico  = ASPECT_ICONS.get(asp, "📌")
                c2   = color_map[score_cls(avg)]
                bg2  = bg_map[score_cls(avg)]
                p2   = bar_pct(avg)
                with asp_cols[i % 4]:
                    st.markdown(f"""
                    <div style="background:white;border:1.5px solid #e5e2d9;border-radius:12px;padding:1rem 1.1rem;margin-bottom:0.9rem;">
                      <div style="font-size:1.3rem;margin-bottom:0.45rem;">{ico}</div>
                      <div style="font-size:0.68rem;font-weight:700;color:#52504a;margin-bottom:0.45rem;">{asp}</div>
                      <div style="font-size:1.3rem;font-weight:800;color:{c2};letter-spacing:-0.03em;line-height:1;">{avg:.1f}<span style="font-size:0.7rem;color:#a09c93;font-weight:400"> /5</span></div>
                      <div style="height:4px;background:#f0ede5;border-radius:4px;overflow:hidden;margin:0.45rem 0 0.3rem;">
                        <div style="width:{p2:.0f}%;height:100%;background:{c2};border-radius:4px;"></div>
                      </div>
                      <div style="font-size:0.6rem;color:#a09c93;">{cnt} mentions</div>
                    </div>""", unsafe_allow_html=True)

            # ── Country view: suggest top cities ────────────────────────────
            if ctype == "country":
                city_agg = sub.groupby("city").agg(
                    avg=("sentiment_score","mean"), n=("sentiment_score","count")
                ).reset_index()
                city_agg = city_agg[city_agg["n"] >= 3].sort_values("avg", ascending=False).head(6)

                if not city_agg.empty:
                    st.markdown(f"""
                    <div style="display:flex;align-items:baseline;gap:0.7rem;margin:2rem 0 1.1rem;">
                      <span style="font-size:1rem;font-weight:800;color:#161410;letter-spacing:-0.02em;">Top Cities in {name}</span>
                      <span style="background:#edf5f3;color:#2a7d6f;font-size:0.58rem;font-weight:700;padding:0.18rem 0.6rem;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;">Based on traveller data</span>
                    </div>""", unsafe_allow_html=True)

                    city_cols = st.columns(min(len(city_agg), 3))
                    for i, (_, crow) in enumerate(city_agg.iterrows()):
                        ccity  = crow["city"]
                        cavg   = crow["avg"]
                        cn     = int(crow["n"])
                        csc    = score_cls(cavg)
                        clbl   = score_lbl(cavg)
                        cimg   = get_img(ccity)
                        ccol   = color_map[csc]
                        cbg    = bg_map[csc]

                        with city_cols[i % 3]:
                            st.markdown(f"""
                            <div style="background:white;border:1.5px solid #e5e2d9;border-radius:14px;overflow:hidden;margin-bottom:0.5rem;box-shadow:0 1px 5px rgba(0,0,0,0.04);">
                              <img src="{cimg}" style="width:100%;height:120px;object-fit:cover;display:block;">
                              <div style="padding:0.9rem 1rem 0.7rem;">
                                <div style="font-size:0.95rem;font-weight:800;color:#161410;letter-spacing:-0.02em;">{ccity}</div>
                                <div style="display:flex;align-items:center;gap:0.5rem;margin-top:0.4rem;">
                                  <span style="font-size:1.3rem;font-weight:800;color:{ccol};letter-spacing:-0.03em;">{cavg:.1f}</span>
                                  <span style="background:{cbg};color:{ccol};font-size:0.57rem;font-weight:700;padding:0.14rem 0.48rem;border-radius:20px;">{clbl}</span>
                                </div>
                                <div style="font-size:0.62rem;color:#a09c93;margin-top:0.25rem;">{cn} mentions</div>
                              </div>
                            </div>""", unsafe_allow_html=True)

                            if st.button(f"Explore {ccity} →", key=f"city_btn_{ccity}_{i}"):
                                st.session_state.update({"view":"detail","city":ccity,"ctype":"city","search_counter": st.session_state.search_counter + 1})
                                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # HOME — TOP 10
    # ══════════════════════════════════════════════════════════════════════════
    else:
        # Sort controls
        sort_opts = ["Overall"] + sorted(ASPECT_ICONS.keys())
        hrow1, hrow2 = st.columns([3, 2])
        with hrow1:
            st.markdown("""
            <div style="display:flex;align-items:baseline;gap:0.7rem;margin-bottom:0.3rem;">
              <span style="font-size:1rem;font-weight:800;color:#161410;letter-spacing:-0.02em;">Top 10 Destinations</span>
              <span style="background:#fef3c7;color:#b45309;font-size:0.58rem;font-weight:700;padding:0.18rem 0.6rem;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;border:1px solid #fde68a;">By traveller sentiment</span>
            </div>""", unsafe_allow_html=True)
        with hrow2:
            st.markdown('<div class="sort-box">', unsafe_allow_html=True)
            sort_by = st.selectbox("Sort by aspect", sort_opts,
                format_func=lambda x: f"Sort by: {x}",
                label_visibility="collapsed", key="sort_asp")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

        t10 = get_top10(df, sort_by)

        if t10.empty:
            st.info("No data yet — run the pipeline first.")
        else:
            cols5 = st.columns(5)
            for i, (_, row) in enumerate(t10.iterrows()):
                city    = row["city"]
                country = row["country"]
                score   = row["avg"]
                n       = int(row["n"])
                sc      = score_cls(score)
                lbl     = score_lbl(score)
                img     = get_img(city)
                col_    = color_map[sc]
                bg_     = bg_map[sc]
                p       = bar_pct(score)

                city_df  = df[df["city"] == city]
                top_asp  = city_df.groupby("aspect_cleaned")["sentiment_score"].mean().sort_values(ascending=False).head(3)

                bars_html = ""
                for asp_n, asp_s in top_asp.items():
                    ico = ASPECT_ICONS.get(asp_n, "📌")
                    ap  = bar_pct(asp_s)
                    ac  = bar_col(asp_s)
                    bars_html += f"""
                    <div style="margin-bottom:0.4rem;">
                      <div style="display:flex;justify-content:space-between;margin-bottom:0.15rem;">
                        <span style="font-size:0.59rem;color:#52504a;">{ico} {asp_n}</span>
                        <span style="font-size:0.59rem;font-weight:700;color:#52504a;">{asp_s:.1f}</span>
                      </div>
                      <div style="height:3px;background:#f0ede5;border-radius:3px;overflow:hidden;">
                        <div style="width:{ap:.0f}%;height:100%;background:{ac};border-radius:3px;"></div>
                      </div>
                    </div>"""

                with cols5[i % 5]:
                    st.markdown(f"""
                    <div style="background:white;border:1.5px solid #e5e2d9;border-radius:16px;overflow:hidden;margin-bottom:0.5rem;box-shadow:0 1px 5px rgba(0,0,0,0.04);display:flex;flex-direction:column;height:380px;">
                      <div style="position:relative;">
                        <img src="{img}" style="width:100%;height:140px;object-fit:cover;display:block;">
                        <div style="position:absolute;top:0.55rem;left:0.55rem;background:rgba(22,20,16,0.72);backdrop-filter:blur(4px);color:white;font-size:0.58rem;font-weight:700;padding:0.16rem 0.5rem;border-radius:20px;">#{i+1}</div>
                      </div>
                      <div style="padding:0.9rem 1rem 0.75rem;flex:1;">
                        <div style="font-size:0.9rem;font-weight:800;color:#161410;letter-spacing:-0.02em;line-height:1.2;min-height:2.4rem;">{city}</div>
                        <div style="font-size:0.65rem;color:#a09c93;margin-bottom:0.65rem;">{country}</div>
                        <div style="display:flex;align-items:center;gap:0.45rem;margin-bottom:0.2rem;">
                          <span style="font-size:1.45rem;font-weight:800;color:{col_};letter-spacing:-0.03em;line-height:1;">{score:.1f}</span>
                          <span style="background:{bg_};color:{col_};font-size:0.57rem;font-weight:700;padding:0.14rem 0.48rem;border-radius:20px;">{lbl}</span>
                        </div>
                        <div style="font-size:0.62rem;color:#a09c93;margin-bottom:0.8rem;">{n:,} mentions</div>
                        {bars_html}
                      </div>
                    </div>""", unsafe_allow_html=True)

                    if st.button("Explore →", key=f"btn_{city}_{i}"):
                        st.session_state.update({"view":"detail","city":city,"ctype":"city"})
                        st.rerun()
                    st.markdown("<div style='margin-bottom:1rem'></div>", unsafe_allow_html=True)

    st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:0.65rem;color:#a09c93;padding-bottom:1rem;">Powered by Reddit r/travel · Analysed daily · City Sentiment Pipeline</div>', unsafe_allow_html=True)