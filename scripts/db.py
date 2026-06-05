import sqlite3

DB_PATH = "../database/futbol380.db"

def get_connection():
    return sqlite3.connect(DB_PATH)