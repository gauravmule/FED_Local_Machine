import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from flask_caching import Cache
from flask_compress import Compress
from flask_bcrypt import Bcrypt
from face_emotion import EmotionDetector
from database_setup import get_db_connection, init_db
import pymysql
from pymysql.cursors import DictCursor
import matplotlib.pyplot as plt
import io
import base64
import cv2
import numpy as np

app = Flask(__name__)
app.secret_key = "super_secret_key_12345"
app.config['CACHE_TYPE'] = 'simple'
app.config['COMPRESS_ALGORITHM'] = 'gzip'

cache = Cache(app)
Compress(app)
bcrypt = Bcrypt(app)
detector = EmotionDetector()

init_db()

@app.route("/")
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return Response(detector.generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/get_emotion_summary")
def get_emotion_summary():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    return jsonify(detector.emotion_summary)

@app.route("/start_session", methods=["POST"])
def start_session():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    if detector.start_session():
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Failed to start session"}), 500

@app.route("/stop_session", methods=["POST"])
def stop_session():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    detector.stop_session()
    return jsonify({"success": True})

@app.route("/predict_emotion", methods=["POST"])
def predict_emotion():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    data = request.json["image"]
    encoded_data = data.split(",")[1]
    image_bytes = base64.b64decode(encoded_data)
    np_arr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    summary = detector.process_client_frame(frame)
    return jsonify(summary)

@app.route("/start_session", methods=["POST"])
def start_session():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    if detector.start_session():  # Still logs session, but no webcam capture
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Failed to start session"}), 500

@app.route("/stop_session", methods=["POST"])
def stop_session():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    detector.stop_session()
    return jsonify({"success": True})

@app.route("/dashboard")
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    emotions = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
    counts = [0] * 7
    sessions = []
    selected_session = request.args.get('session_id', '')
    stats = {"total_sessions": 0, "total_faces_detected": 0, "most_common_emotion": "N/A"}

    if conn:
        try:
            with conn.cursor(DictCursor) as cursor:
                cursor.execute('SELECT id, start_time FROM sessions WHERE user_id = %s ORDER BY start_time DESC', (session['user_id'],))
                sessions = cursor.fetchall()

                query = '''
                    SELECT emotion, COUNT(*) as count 
                    FROM emotion_logs 
                    WHERE session_id IN (SELECT id FROM sessions WHERE user_id = %s)
                '''
                params = [session['user_id']]
                if selected_session:
                    query += ' AND session_id = %s'
                    params.append(selected_session)
                query += ' GROUP BY emotion'
                cursor.execute(query, params)
                emotion_dist = cursor.fetchall()
                for e in emotion_dist:
                    if e['emotion'] in emotions:
                        idx = emotions.index(e['emotion'])
                        counts[idx] = e['count']

                cursor.execute('SELECT * FROM dashboard_stats WHERE id = 1')
                stats = cursor.fetchone() or stats

        except pymysql.MySQLError as e:
            flash(f"Database error: {e.args[1]}", "error")
        finally:
            conn.close()

    # Generate bar chart
    plt.figure(figsize=(8, 5))
    plt.bar(emotions, counts, color=['#FF6384', '#FF9F40', '#FFCD56', '#4BC0C0', '#36A2EB', '#9966FF', '#C9CBCF'], edgecolor='black')
    plt.title(f'Emotion Distribution {"(Session #" + selected_session + ")" if selected_session else "(All Sessions)"}', fontsize=14, pad=10)
    plt.xlabel('Emotions', fontsize=12)
    plt.ylabel('Count', fontsize=12)
    plt.ylim(0, max(counts, default=0) + 2)
    plt.xticks(rotation=45, ha='right', fontsize=10)
    plt.yticks(fontsize=10)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()

    bar_img = io.BytesIO()
    plt.savefig(bar_img, format='png', bbox_inches='tight', dpi=100)
    plt.close()
    bar_img.seek(0)
    bar_chart_data = base64.b64encode(bar_img.getvalue()).decode('utf-8')

    # Generate pie chart only if there’s data
    if sum(counts) > 0:  # Check if counts has non-zero values
        plt.figure(figsize=(5, 5))
        plt.pie(counts, labels=emotions, colors=['#FF6384', '#FF9F40', '#FFCD56', '#4BC0C0', '#36A2EB', '#9966FF', '#C9CBCF'], autopct='%1.1f%%', startangle=90, textprops={'fontsize': 10})
        plt.title('Emotion Proportions', fontsize=14, pad=10)

        pie_img = io.BytesIO()
        plt.savefig(pie_img, format='png', bbox_inches='tight', dpi=100)
        plt.close()
        pie_img.seek(0)
        pie_chart_data = base64.b64encode(pie_img.getvalue()).decode('utf-8')
    else:
        # Placeholder for no data
        pie_chart_data = None  # Pass None if no data; handle in template

    return render_template("dashboard.html", bar_chart_data=bar_chart_data, pie_chart_data=pie_chart_data, sessions=sessions, selected_session=selected_session, stats=stats)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db_connection()
        if not conn:
            flash("Database unavailable", "error")
            return redirect(url_for('login'))

        try:
            with conn.cursor(DictCursor) as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()
                
                if user and bcrypt.check_password_hash(user['password'], password):
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    return redirect(url_for('index'))
                else:
                    flash("Invalid credentials", "error")
        except pymysql.MySQLError as e:
            flash(f"Database error: {e.args[1]}", "error")
        finally:
            conn.close()
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Both fields are required", "error")
            return redirect(url_for('signup'))

        conn = get_db_connection()
        if not conn:
            flash("Database unavailable", "error")
            return redirect(url_for('signup'))

        try:
            hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (username, password) VALUES (%s, %s)",
                    (username, hashed_pw)
                )
                conn.commit()
                flash("Account created!", "success")
                return redirect(url_for('login'))
        except pymysql.IntegrityError:
            flash("Username already exists", "error")
        except pymysql.MySQLError as e:
            flash(f"Database error: {e.args[1]}", "error")
        finally:
            conn.close()
    
    return render_template("signup.html")

@app.route("/edit_account", methods=["GET", "POST"])
def edit_account():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "error")
        return redirect(url_for('index'))

    try:
        if request.method == "POST":
            new_username = request.form["username"]
            new_password = bcrypt.generate_password_hash(request.form["password"]).decode("utf-8")

            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET username = %s, password = %s WHERE id = %s",
                    (new_username, new_password, session["user_id"])
                )
                conn.commit()
                session["username"] = new_username
                flash("Account updated successfully!", "success")
                return redirect(url_for("index"))

        return render_template("edit_account.html")
    except pymysql.MySQLError as e:
        flash(f"Database error: {e.args[1]}", "error")
        return redirect(url_for('index'))
    finally:
        conn.close()

@app.route("/delete_account", methods=["POST"])
def delete_account():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database error"}), 500

    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (session["user_id"],))
            conn.commit()
            session.clear()
            flash("Account deleted successfully.", "success")
            return jsonify({"success": True})
    except pymysql.MySQLError as e:
        return jsonify({"success": False, "message": f"Database error: {e.args[1]}"}), 500
    finally:
        conn.close()

@app.route("/about_us")
def about_us():
    return render_template("about_us.html")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)