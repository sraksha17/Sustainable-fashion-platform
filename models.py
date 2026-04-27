import os
import re
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv('MONGODB_URI')  # note: matches .env
DB_NAME = os.getenv('MONGO_DB')       # optional override

client = MongoClient(MONGO_URI)

if DB_NAME:
    db = client[DB_NAME]
else:
    # Extract database name from URI (the part after last / before ?)
    match = re.search(r'/([^/?]+)(\?|$)', MONGO_URI)
    if match:
        db_name = match.group(1)
        db = client[db_name]
    else:
        db = client.get_default_database()

def get_db():
    return db