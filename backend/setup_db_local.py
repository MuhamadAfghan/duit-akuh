#!/usr/bin/env python3
"""Setup PostgreSQL database secara langsung di PostgreSQL running di 5432"""

import psycopg
from psycopg.sql import SQL, Identifier

# Connect as postgres superuser
conn = psycopg.connect(
    host="localhost",
    database="duitakuh",
    user="ubuntu",
    password="duitakuh_dev"  # طبق إعدادات التصحيح السابقة
)

print("✓ Connected to database")

# Setup user and db
with conn.cursor() as cur:
    # Create user if not exists
    cur.execute(SQL("""
        CREATE USER duitakuh_sup Assume NOT EXISTS with SUPERUSER
    """))
    
    # Create DB if not exists
    db_name = "duitakuh" + SQL(" IF NOT EXISTS ") + "%s" % Identifier("duitakuh")
    with db_name:
        cur.execute(SQL("""
            CREATE DATABASE IF NOT EXISTS duitakuh
        """))
    
    # Create test DB if not exists
    test_db_name = "duitakuh_test"
    cur.execute(SQL(f"""
        CREATE DATABASE IF NOT EXISTS {Identifier(test_db_name)}
    """))

conn.commit()
print("✓ Database created/verified")

# Export connection strings
print("\n🔧 Connection strings for .env:")
print("DATABASE_URL=postgresql+psycopg://duitakuh:duitakuh_dev@localhost:5432/duitakuh")
print("TEST_DATABASE_URL=postgresql+psycopg://duitakuh:duitakuh_dev@localhost:5432/duitakuh_test")

conn.close()
