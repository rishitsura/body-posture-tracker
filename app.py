import cv2
import threading
import numpy as np
import time
from flask import Flask, render_template, Response, request, jsonify
from posture_detection import ExerciseDetector

app = Flask(__name__)

# Global variables
detector = None
output_frame = None
lock = threading.Lock()

def generate_frames():
    global output_frame, detector
    
    # Create a black frame as placeholder with larger dimensions
    black_frame = np.zeros((600, 800, 3), dtype=np.uint8)  # Updated dimensions
    
    while True:
        try:
            time.sleep(0.03)  # ~30 fps
            with lock:
                frame_to_display = output_frame.copy() if output_frame is not None else black_frame.copy()
            
            # Remove the color conversion to keep natural colors
            ret, buffer = cv2.imencode('.jpg', frame_to_display, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                continue
                
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print(f"Error in generate_frames: {e}")
            continue

def update_frame():
    global output_frame, detector
    
    frame_count = 0
    last_log_time = time.time()
    
    while detector and detector.running:
        try:
            time.sleep(0.01)  # Reduce CPU usage
            current_time = time.time()
            
            if detector.current_frame is not None:
                with lock:
                    output_frame = detector.current_frame.copy()
                    frame_count += 1
                
                # Log frame rate every 5 seconds
                if current_time - last_log_time > 5:
                    fps = frame_count / (current_time - last_log_time)
                    print(f"Frame update rate: {fps:.2f} fps")
                    frame_count = 0
                    last_log_time = current_time
        except Exception as e:
            print(f"Error in update_frame: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    # Set response headers to prevent caching
    response = Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/start', methods=['POST'])
def start_detection():
    global detector, output_frame
    exercise_type = request.json.get('exercise_type', 'hand_raise')
    
    if detector is not None and detector.running:
        return jsonify({"status": "Detection already running"})
    
    # Clear previous frame
    output_frame = None
    
    detector = ExerciseDetector()
    detector.exercise_type = exercise_type
    detector.start()
    
    # Start a thread to update frames
    frame_thread = threading.Thread(target=update_frame, daemon=True)
    frame_thread.start()
    
    return jsonify({"status": "Detection started"})

@app.route('/stop', methods=['POST'])
def stop_detection():
    global detector, output_frame
    
    if detector is None or not detector.running:
        return jsonify({"status": "Detection not running"})
    
    detector.stop()
    output_frame = None
    
    return jsonify({"status": "Detection stopped"})

@app.route('/status', methods=['GET'])
def get_status():
    global detector
    
    if detector is None:
        return jsonify({
            "running": False,
            "feedback": "",
            "angle": "",
            "exercise_type": ""
        })
    
    return jsonify({
        "running": detector.running,
        "feedback": detector.feedback_text,
        "angle": detector.angle_text,
        "form_status": detector.form_status,
        "exercise_type": detector.exercise_type
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
