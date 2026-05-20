from pymongo import MongoClient
from dotenv import load_dotenv
import os
load_dotenv()
db = MongoClient(os.getenv('MONGO_URI'))[os.getenv('MONGO_DB_NAME', 'travel_pipeline_db')]
result = db['city_weekly_features'].update_many(
    {'week_start': '2026-03-23'},
    {'$set': {'week_start': '2026-04-24'}}
)
print('Updated:', result.modified_count, 'docs')