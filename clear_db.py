#!/usr/bin/env python3
"""
clear_db.py - Clear all data from tasks, journal, and logs tables.
Keeps the table structures intact for a fresh start.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///stash.db"


def clear_database():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Delete all records from each table
        session.execute(text("DELETE FROM tasks"))
        session.execute(text("DELETE FROM journal"))
        session.execute(text("DELETE FROM activity_log"))
        session.commit()

        # Run VACUUM to reclaim disk space
        session.execute(text("VACUUM"))

        print("✓ Database cleared successfully!")
        print("  - tasks table: cleared")
        print("  - journal table: cleared")
        print("  - activity_log table: cleared")

    except Exception as e:
        session.rollback()
        print(f"Error clearing database: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    clear_database()
