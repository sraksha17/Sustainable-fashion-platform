import os
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime

load_dotenv()

# Connect to MongoDB
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("MONGO_DB", "revive_threads")]

print("Connected to database.")

# 1. Delete all sales records
sales_collection = db["sales"]
deleted_sales = sales_collection.delete_many({})
print(f"Deleted {deleted_sales.deleted_count} sales records.")

# 2. Reset finished designs that were sold back to "available"
designs_collection = db["finished_designs"]
updated = designs_collection.update_many(
    {"status": "sold"},
    {"$set": {"status": "available"}}
)
print(f"Reset {updated.modified_count} designs from sold to available.")

# Optional: clear any designer projects that are "completed" (if they were completed via sale)
# Uncomment if you want to reset all completed projects to in_progress:
# projects_collection = db["designer_projects"]
# reset_projects = projects_collection.update_many(
#     {"status": "completed"},
#     {"$set": {"status": "in_progress", "completed_at": None, "finished_design_id": None}}
# )
# print(f"Reset {reset_projects.modified_count} designer projects.")

# Optional: clear notifications related to sales (if any)
# notifications_collection = db["notifications"]
# deleted_notifications = notifications_collection.delete_many({"type": "sale"})
# print(f"Deleted {deleted_notifications.deleted_count} sale notifications.")

print("Reset complete.")