import pymysql
from pymysql.cursors import DictCursor

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
        return pymysql.connect(**db_config)
    except pymysql.MySQLError as e:
        print(f"Database connection failed: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database during initialization")
        return

    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    start_time DATETIME,
                    end_time DATETIME,
                    total_faces INT DEFAULT 0,
                    most_common_emotion VARCHAR(20),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS emotion_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id INT,
                    emotion VARCHAR(20),
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dashboard_stats (
                    id INT PRIMARY KEY DEFAULT 1,
                    total_sessions INT DEFAULT 0,
                    total_faces_detected INT DEFAULT 0,
                    most_common_emotion VARCHAR(20),
                    last_updated DATETIME,
                    CHECK (id = 1)
                )
            ''')
            
            cursor.execute('''
                INSERT IGNORE INTO dashboard_stats (id, total_sessions, total_faces_detected, most_common_emotion, last_updated)
                VALUES (1, 0, 0, 'N/A', NOW())
            ''')
            
        print("Database initialized successfully")
    except pymysql.MySQLError as e:
        print(f"Database initialization failed: {e}")
    finally:
        conn.close()