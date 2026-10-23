import mysql.connector
from mysql.connector import pooling
from config import Config

# Create a small connection pool
connection_pool = pooling.MySQLConnectionPool(
    pool_name="studybuddy_pool",
    pool_size=5,
    host=Config.DB_HOST,
    port=Config.DB_PORT,
    database=Config.DB_NAME,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
    autocommit=True,
)


def get_db():
    """Get a pooled DB connection."""
    return connection_pool.get_connection()