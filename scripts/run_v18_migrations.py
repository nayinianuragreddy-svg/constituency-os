import pathlib
import sys
from importlib import import_module

from sqlalchemy import create_engine, inspect

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import DATABASE_URL
from app.db import init_db

MIGRATIONS = [
    "migrations.v18_000_create_offices",
    "migrations.v18_001_extend_citizens",
    "migrations.v18_002_extend_tickets",
    "migrations.v18_003_extend_officer_mappings",
    "migrations.v18_004_create_complaint_categories",
    "migrations.v18_005_create_mandals",
    "migrations.v18_006_create_wards",
    "migrations.v18_007_create_citizen_conversations",
    "migrations.v18_008_create_ticket_custom_fields",
    "migrations.v18_009_create_daily_ticket_sequences",
    "migrations.v18_010_create_media_uploads",
]

engine = create_engine(DATABASE_URL)
if not inspect(engine).has_table("citizens"):
    print("Base tables not found, running init_db() first.")
    init_db()

with engine.begin() as conn:
    for module_name in MIGRATIONS:
        module = import_module(module_name)
        module.run(conn)
        print(f"applied {module_name}")