import pymysql
from pymysql.cursors import DictCursor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_config = {
    "host": "localhost",
    "user": "root",
    "password": "admin@123",
    "database": "face_emotion_detection",
    "cursorclass": DictCursor,
    "autocommit": True,
    "charset": "utf8mb4"
}

def get_db_connection():
    try:
        test_conn = pymysql.connect(
            host="localhost",
            user="root",
            password="admin@123",
            autocommit=True
        )
        with test_conn.cursor() as cursor:
            cursor.execute("CREATE DATABASE IF NOT EXISTS face_emotion_detection")
            logger.info("Database verified/created")
        test_conn.close()
        
        conn = pymysql.connect(**db_config)
        logger.info("Database connection successful!")
        return conn
    except pymysql.MySQLError as e:
        logger.error(f"Connection failed: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to initialize database: No connection")
        return

    try:
        with conn.cursor() as cursor:
            tables = [
                '''CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(128) NOT NULL
                ) ENGINE=InnoDB''',
                
                '''CREATE TABLE IF NOT EXISTS sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    end_time DATETIME,
                    total_faces INT DEFAULT 0,
                    most_common_emotion VARCHAR(50),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB''',
                
                '''CREATE TABLE IF NOT EXISTS emotion_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id INT,
                    emotion VARCHAR(50),
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                ) ENGINE=InnoDB''',
                
                '''CREATE TABLE IF NOT EXISTS dashboard_stats (
                    id INT PRIMARY KEY DEFAULT 1,
                    total_sessions INT DEFAULT 0,
                    total_faces_detected INT DEFAULT 0,
                    most_common_emotion VARCHAR(50),
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB'''
            ]

            for table in tables:
                try:
                    cursor.execute(table)
                except pymysql.MySQLError as e:
                    logger.error(f"Table creation error: {e}")

            try:
                cursor.execute('''
                    INSERT INTO dashboard_stats (id)
                    VALUES (1)
                    ON DUPLICATE KEY UPDATE id = id
                ''')
            except pymysql.MySQLError as e:
                logger.error(f"Stats init error: {e}")

            conn.commit()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Init error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    init_db()