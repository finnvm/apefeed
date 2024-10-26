# database_setup.py
import sqlite3

def create_tables():
    conn = sqlite3.connect('apefeed.db')
    cursor = conn.cursor()

    # Create videos table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        url TEXT UNIQUE NOT NULL,
        publish_date TEXT NOT NULL,
        tags TEXT NOT NULL,
        date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_tables()
