import cv2
import threading
import time
import queue
import numpy as np
from fer import FER
from database_setup import get_db_connection
from flask import session
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmotionDetector:
    def __init__(self):
        self.cap = None
        self.is_running = False
        self.lock = threading.Lock()
        self.emotion_summary = {"total_faces": 0, "emotions": {}}
        self.face_tracker = {}
        self.frame_queue = queue.Queue(maxsize=3)
        self.processed_frame = None
        self.tracking_threshold = 75
        self.emotion_analysis_interval = 1
        self.frame_counter = 0
        self.session_id = None
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self.emotion_detector = FER(mtcnn=False)

    def _analyze_emotion(self, face_roi):
        try:
            result = self.emotion_detector.detect_emotions(face_roi)
            if result and len(result) > 0:
                emotions = result[0]['emotions']
                dominant_emotion = max(emotions, key=emotions.get)
                logger.info(f"Emotions detected: {emotions}")
                return dominant_emotion
            logger.info("No emotions detected in frame")
            return "neutral"
        except Exception as e:
            logger.error(f"Emotion analysis error: {e}")
            return "neutral"

    def start_session(self):
        with self.lock:
            if self.is_running:
                return False
            
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                logger.error("Error: Webcam not accessible!")
                return False
            
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 24)
            self.is_running = True

            conn = get_db_connection()
            if conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute('''
                            INSERT INTO sessions (user_id, start_time)
                            VALUES (%s, NOW())
                        ''', (session.get('user_id'),))
                        self.session_id = cursor.lastrowid
                        cursor.execute('''
                            UPDATE dashboard_stats 
                            SET total_sessions = total_sessions + 1
                            WHERE id = 1
                        ''')
                        conn.commit()
                    logger.info(f"Session started with ID: {self.session_id}")
                except Exception as e:
                    logger.error(f"Database error: {e}")
                    self.session_id = None
                finally:
                    conn.close()
            else:
                logger.error("No database connection for session start")
                self.is_running = False
                return False

            self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
            self.process_thread = threading.Thread(target=self._process_frames, daemon=True)
            self.capture_thread.start()
            self.process_thread.start()
            return True

    def stop_session(self):
        with self.lock:
            if not self.is_running or not self.cap:
                return
            
            self.is_running = False
            if self.cap and self.cap.isOpened():
                self.cap.release()
                self.cap = None

            if self.capture_thread:
                self.capture_thread.join(timeout=5)
            if self.process_thread:
                self.process_thread.join(timeout=5)

            conn = get_db_connection()
            if conn and self.session_id:
                try:
                    with conn.cursor() as cursor:
                        for fid, (_, emotion, _) in self.face_tracker.items():
                            if emotion:
                                cursor.execute('''
                                    INSERT INTO emotion_logs (session_id, emotion)
                                    VALUES (%s, %s)
                                ''', (self.session_id, emotion))
                        
                        cursor.execute('''
                            UPDATE sessions SET
                                end_time = NOW(),
                                total_faces = %s,
                                most_common_emotion = %s
                            WHERE id = %s
                        ''', (self.emotion_summary['total_faces'],
                              max(self.emotion_summary['emotions'], key=self.emotion_summary['emotions'].get, default='neutral'),
                              self.session_id))
                        
                        cursor.execute('''
                            UPDATE dashboard_stats SET
                                total_faces_detected = total_faces_detected + %s,
                                most_common_emotion = COALESCE(
                                    (SELECT emotion 
                                     FROM emotion_logs 
                                     GROUP BY emotion 
                                     ORDER BY COUNT(*) DESC 
                                     LIMIT 1),
                                    most_common_emotion
                                ),
                                last_updated = NOW()
                            WHERE id = 1
                        ''', (self.emotion_summary['total_faces'],))
                        
                        conn.commit()
                    logger.info(f"Session {self.session_id} stopped and logged")
                except Exception as e:
                    logger.error(f"Database error: {e}")
                finally:
                    conn.close()

            self.face_tracker = {}
            self.emotion_summary = {"total_faces": 0, "emotions": {}}
            self.session_id = None

    def _capture_frames(self):
        while self.is_running:
            try:
                ret, frame = self.cap.read()
                if ret and not self.frame_queue.full():
                    self.frame_queue.put(cv2.resize(frame, (320, 240)))
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"Capture frame error: {e}")
                break

    def _process_frames(self):
        while self.is_running:
            try:
                if self.frame_queue.empty():
                    time.sleep(0.01)
                    continue

                small_frame = self.frame_queue.get()
                self.frame_counter += 1
                
                gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.05, 3, minSize=(30, 30))
                
                frame = cv2.resize(small_frame, (640, 480))
                current_emotions = []
                new_tracker = {}

                for (x, y, w, h) in faces:
                    x *= 2; y *= 2; w *= 2; h *= 2
                    face_roi = frame[y:y+h, x:x+w]
                    
                    emotion = self._analyze_emotion(face_roi)
                    
                    centroid = (x + w//2, y + h//2)
                    closest_id = None
                    min_dist = float('inf')
                    
                    for fid, (old_cent, _, _) in self.face_tracker.items():
                        dist = ((centroid[0]-old_cent[0])**2 + (centroid[1]-old_cent[1])**2)**0.5
                        if dist < min_dist and dist < self.tracking_threshold:
                            min_dist = dist
                            closest_id = fid
                    
                    fid = closest_id if closest_id else len(self.face_tracker)
                    new_tracker[fid] = (centroid, emotion, (x, y, w, h))
                    current_emotions.append(emotion)
                    
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    cv2.putText(frame, f"{emotion} (ID: {fid})", (x, y-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                self.face_tracker = new_tracker
                emotion_counts = {e: current_emotions.count(e) for e in set(current_emotions)}
                self.emotion_summary = {
                    "total_faces": len(faces),
                    "emotions": emotion_counts if emotion_counts else {"neutral": 0}
                }
                
                self.processed_frame = frame
            except Exception as e:
                logger.error(f"Process frame error: {e}")
                break

    def generate_frames(self):
        while self.is_running:
            try:
                if self.processed_frame is not None:
                    ret, buffer = cv2.imencode('.jpg', self.processed_frame)
                    frame_data = (b'--frame\r\n'
                                 b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                    yield frame_data
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"Generate frames error: {e}")
                break