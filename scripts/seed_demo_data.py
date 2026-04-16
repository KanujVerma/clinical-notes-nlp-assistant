#!/usr/bin/env python3
# scripts/seed_demo_data.py
"""
Load dev + showcase notes (60 total) into the database.
Eval notes are held out — they are never seeded into the reviewer DB.
Run this script before demoing the app.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from utils.db import get_engine, init_db, get_session
from routes.seed import seed_notes
from config import Config

if __name__ == "__main__":
    engine = get_engine(Config.DB_PATH)
    init_db(engine)
    session = get_session(engine)
    result = seed_notes(session)
    session.close()
    print(f"Seeded: {result['loaded']} loaded, {result['skipped']} already existed.")
