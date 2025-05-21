import cv2
import mediapipe as mp
import math
import threading
from playsound import playsound
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import numpy as np

# Constants for exercise angles
HAND_RAISE_MIN_ANGLE = 150  # Minimum angle for hand raise
HAND_CURL_MAX_ANGLE = 120  # Maximum angle for hand curl


class ExerciseDetector:
    def __init__(self):
        self.running = False
        self.exercise_type = "hand_raise"
        self.cap = None
        self.detection_thread = None
        self.current_frame = None
        self.feedback_text = ""
        self.angle_text = ""
        self.form_status = ""
        self.lock = threading.Lock()  # Add a lock for thread safety with web app
        self.camera_index = 0  # Default camera index

    def calculate_angle(self, a, b, c):
        """Calculates angle at point b"""
        ba = (a[0] - b[0], a[1] - b[1])
        bc = (c[0] - b[0], c[1] - b[1])

        dot_product = ba[0] * bc[0] + ba[1] * bc[1]
        magnitude_ba = math.sqrt(ba[0] ** 2 + ba[1] ** 2)
        magnitude_bc = math.sqrt(bc[0] ** 2 + bc[1] ** 2)

        if magnitude_ba * magnitude_bc == 0:
            return 0

        angle_rad = math.acos(dot_product / (magnitude_ba * magnitude_bc))
        return math.degrees(angle_rad)

    def is_exercise_incorrect(self, shoulder_angle, elbow_angle, exercise_type):
        """Check if exercise form is incorrect"""
        if exercise_type == "hand_raise":
            return (
                shoulder_angle < HAND_RAISE_MIN_ANGLE
            )  # Only detect if arm not raised enough
        elif exercise_type == "hand_curl":
            return (
                elbow_angle > HAND_CURL_MAX_ANGLE
            )  # Only detect if arm extended too much
        return False

    def play_alarm_sound(self):
        import os
        import threading
        try:
            # First, try to find alarm.wav in the current directory
            file_dir = os.path.dirname(os.path.realpath(__file__))
            alarm_path = os.path.join(file_dir, "alarm.wav")
            
            # If alarm.wav doesn't exist, use a default sound
            if not os.path.exists(alarm_path):
                print(f"Warning: alarm.wav not found at {alarm_path}. Using alternative method.")
                import winsound
                # Play Windows default sound (asterisk)
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
            else:
                # Use playsound as originally intended
                print(f"Playing sound from: {alarm_path}")
                playsound(alarm_path)
                
        except Exception as e:
            print(f"Error playing sound: {e}")
            try:
                # Fallback to winsound on Windows
                import winsound
                winsound.Beep(1000, 500)  # Frequency 1000Hz, duration 500ms
            except:
                print("Could not play any sound!")

    def get_landmark_coords(self, landmarks, landmark_point, w, h):
        """Get coordinates for a landmark point"""
        return (
            int(landmarks[landmark_point].x * w),
            int(landmarks[landmark_point].y * h),
        )

    def detection_loop(self):
        import time  # Ensure time is imported
        print("Detection loop started. Attempting to open camera...")
        indices_to_try = [0, 1, 2]
        camera_opened = False

        for camera_index in indices_to_try:
            print(f"Trying camera index {camera_index}...")
            self.cap = cv2.VideoCapture(camera_index)
            time.sleep(1)  # wait for the camera to initialize
            if self.cap.isOpened():
                self.camera_index = camera_index
                camera_opened = True
                print(f"Successfully opened camera with index {camera_index}")
                break
            else:
                print(f"Failed to open camera with index {camera_index}")

        if not camera_opened:
            print("Error: Could not open any camera, retrying...")
            time.sleep(5)
            self.cap = cv2.VideoCapture(0)
            time.sleep(1)
            if self.cap.isOpened():
                camera_opened = True
                self.camera_index = 0
                print("Opened camera with index 0 on retry")
            else:
                print("Failed to open camera on retry; aborting detection loop")
                self.running = False
                return

        # Set camera resolution and properties for better performance
        try:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)  # Increased from 640
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)  # Increased from 480
            self.cap.set(cv2.CAP_PROP_FPS, 30)  # Try to set FPS to 30
            print(f"Camera properties set: {self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)} @ {self.cap.get(cv2.CAP_PROP_FPS)} fps")
        except Exception as e:
            print(f"Warning: Could not set camera properties: {e}")
        
        mp_pose = mp.solutions.pose
        pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        mp_draw = mp.solutions.drawing_utils
        
        # Initialize the current_frame with a black frame to avoid None
        with self.lock:
            self.current_frame = np.zeros((600, 800, 3), dtype=np.uint8)  # Updated dimensions
        
        wrong_form_counter = 0
        threshold_wrong_frames = 15  # Reduced from 30 for quicker response
        frame_count = 0
        start_time = time.time()
        
        # Add state tracking to prevent flickering
        last_form_status = None
        form_stable_count = 0
        form_stability_threshold = 5  # Frames to wait before changing form status
        
        # Add variables for stabilizing feedback
        stable_feedback_text = ""
        stable_form_status = ""
        alarm_triggered = False
        consecutive_wrong_frames = 0
        
        print("Starting detection loop...")
        while self.running:
            try:
                # Read a frame from the camera
                ret, frame = self.cap.read()
                if not ret:
                    print("Failed to read frame from camera")
                    # Short delay to avoid CPU spinning if camera fails
                    time.sleep(0.1)
                    continue
                
                frame_count += 1
                current_time = time.time()
                elapsed_time = current_time - start_time
                
                # Log FPS every 5 seconds
                if elapsed_time > 5:
                    fps = frame_count / elapsed_time
                    print(f"Camera capturing at {fps:.2f} FPS")
                    frame_count = 0
                    start_time = current_time
                
                # Process the frame
                frame = cv2.flip(frame, 1)  # Horizontal flip (mirror)
                
                # Only do pose detection on every second frame to improve performance
                process_this_frame = (frame_count % 2 == 0)
                
                if process_this_frame:
                    # Convert to RGB for pose detection
                    image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image_rgb.flags.writeable = False
                    results = pose.process(image_rgb)
                    image_rgb.flags.writeable = True
                    image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
                    
                    if results.pose_landmarks:
                        mp_draw.draw_landmarks(
                            image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS
                        )

                        h, w, _ = image.shape
                        landmarks = results.pose_landmarks.landmark

                        # Get required landmarks
                        left_wrist = self.get_landmark_coords(
                            landmarks, mp_pose.PoseLandmark.LEFT_WRIST.value, w, h
                        )
                        left_elbow = self.get_landmark_coords(
                            landmarks, mp_pose.PoseLandmark.LEFT_ELBOW.value, w, h
                        )
                        left_shoulder = self.get_landmark_coords(
                            landmarks, mp_pose.PoseLandmark.LEFT_SHOULDER.value, w, h
                        )
                        left_hip = self.get_landmark_coords(
                            landmarks, mp_pose.PoseLandmark.LEFT_HIP.value, w, h
                        )

                        # Calculate angles
                        shoulder_angle = self.calculate_angle(
                            left_elbow, left_shoulder, left_hip
                        )
                        elbow_angle = self.calculate_angle(
                            left_wrist, left_elbow, left_shoulder
                        )

                        # Update angle text and feedback instantly
                        with self.lock:
                            if self.exercise_type == "hand_raise":
                                self.angle_text = f"Shoulder Angle: {int(shoulder_angle)}°"
                            else:
                                self.angle_text = f"Elbow Angle: {int(elbow_angle)}°"

                        # Determine the current form status
                        is_incorrect = self.is_exercise_incorrect(
                            shoulder_angle, elbow_angle, self.exercise_type
                        )
                        
                        # Count consecutive frames with wrong form
                        if is_incorrect:
                            consecutive_wrong_frames += 1
                            if consecutive_wrong_frames >= 5:  # Stabilize for at least 5 frames
                                wrong_form_counter += 1
                                # Set form status to bad only when stable
                                if stable_form_status != "bad":
                                    stable_form_status = "bad"
                                    if self.exercise_type == "hand_raise":
                                        stable_feedback_text = "Warning: Raise your arm higher"
                                    else:
                                        stable_feedback_text = "Warning: Curl your arm more"
                                    
                                    # Update the shared data
                                    with self.lock:
                                        self.form_status = "bad"
                                        self.feedback_text = stable_feedback_text
                        else:
                            # Reset wrong form counter on good form
                            consecutive_wrong_frames = 0
                            wrong_form_counter = 0
                            
                            # Set form status to good when stable
                            if stable_form_status != "good":
                                stable_form_status = "good"
                                stable_feedback_text = "Good Form!"
                                
                                # Update the shared data
                                with self.lock:
                                    self.form_status = "good"
                                    self.feedback_text = stable_feedback_text
                        
                        # Trigger alarm after threshold (only once per sequence)
                        if wrong_form_counter >= threshold_wrong_frames and not alarm_triggered:
                            alarm_triggered = True
                            cv2.putText(
                                image,
                                "ALARM: Fix Your Form!",
                                (50, 120),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                1,
                                (0, 0, 255),
                                3,
                            )
                            # Play sound in a separate thread with clear print indication
                            print("TRIGGERING ALARM SOUND NOW!")
                            alarm_thread = threading.Thread(target=self.play_alarm_sound, daemon=True)
                            alarm_thread.start()
                            
                            # Reset wrong form counter after alarm
                            wrong_form_counter = 0
                        
                        # If form is good for a while, reset alarm trigger
                        if stable_form_status == "good" and consecutive_wrong_frames == 0:
                            alarm_triggered = False
                        
                        # Always show angle text
                        cv2.putText(
                            image,
                            self.angle_text,
                            (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 255),
                            2,
                        )
                        
                        # Show stable feedback text (doesn't flicker)
                        feedback_color = (0, 255, 0) if stable_form_status == "good" else (0, 0, 255)
                        cv2.putText(
                            image,
                            stable_feedback_text,
                            (10, 90),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            feedback_color,
                            2,
                        )
                    else:
                        # If no landmarks, continue displaying last feedback without change
                        pass
                else:
                    image = frame
                
                # Always update the current frame, even if we skipped pose detection
                with self.lock:
                    self.current_frame = image.copy()
                    
            except Exception as e:
                print(f"Error in detection loop: {e}")
                time.sleep(0.1)  # Avoid tight loop on error
        
        print("Detection loop stopped, releasing camera...")
        if self.cap:
            self.cap.release()
        
        print("Camera released.")

    def start(self):
        """Start the exercise detection"""
        if not self.running:
            self.running = True
            self.detection_thread = threading.Thread(target=self.detection_loop)
            self.detection_thread.start()

    def stop(self):
        """Stop the exercise detection"""
        self.running = False
        if self.detection_thread:
            self.detection_thread.join()
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()


class ExerciseGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Exercise Form Monitor")
        self.root.geometry("800x600")
        
        # Create ExerciseDetector instance
        self.detector = ExerciseDetector()
        
        # Create UI elements
        self.create_widgets()
        
        # Update flag
        self.is_updating = False
        
    def create_widgets(self):
        # Top frame for controls
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Start/Stop button
        self.start_stop_btn = ttk.Button(control_frame, text="Start", command=self.toggle_detection)
        self.start_stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Exercise selection
        ttk.Label(control_frame, text="Exercise:").pack(side=tk.LEFT, padx=5)
        
        self.exercise_var = tk.StringVar(value="hand_raise")
        exercise_combo = ttk.Combobox(
            control_frame, 
            textvariable=self.exercise_var,
            values=["hand_raise", "hand_curl"],
            state="readonly",
            width=15
        )
        exercise_combo.pack(side=tk.LEFT, padx=5)
        exercise_combo.bind("<<ComboboxSelected>>", self.change_exercise)
        
        # Status labels
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.angle_label = ttk.Label(status_frame, text="Angle: Not detected")
        self.angle_label.pack(side=tk.LEFT, padx=5)
        
        self.feedback_label = ttk.Label(status_frame, text="")
        self.feedback_label.pack(side=tk.RIGHT, padx=5)
        
        # Video frame
        self.video_frame = ttk.Frame(self.root, borderwidth=2, relief="groove")
        self.video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.video_label = ttk.Label(self.video_frame)
        self.video_label.pack(fill=tk.BOTH, expand=True)
        
        # Instructions label
        instructions = (
            "Instructions:\n"
            "1. Select an exercise type from the dropdown menu\n"
            "2. Click 'Start' to begin monitoring\n"
            "3. Position yourself so your body is visible in the camera\n"
            "4. For Hand Raise: Raise your arm straight up\n"
            "5. For Hand Curl: Perform bicep curls with proper form"
        )
        
        ttk.Label(self.root, text=instructions, justify=tk.LEFT).pack(
            padx=10, pady=(0, 10), anchor=tk.W
        )
        
    def update_video(self):
        if self.detector.running and self.detector.current_frame is not None:
            # Convert OpenCV image to PIL format for Tkinter
            image = Image.fromarray(self.detector.current_frame)
            
            # Resize to fit the frame if needed
            frame_width = self.video_frame.winfo_width()
            frame_height = self.video_frame.winfo_height()
            
            if frame_width > 1 and frame_height > 1:
                image = image.resize((frame_width, frame_height), Image.LANCZOS)
                
            # Convert to Tkinter format
            img_tk = ImageTk.PhotoImage(image=image)
            
            # Update label
            self.video_label.configure(image=img_tk)
            self.video_label.image = img_tk
            
            # Update status labels
            self.angle_label.configure(text=self.detector.angle_text if self.detector.angle_text else "Angle: Not detected")
            
            if self.detector.form_status == "good":
                self.feedback_label.configure(text=self.detector.feedback_text, foreground="green")
            elif self.detector.form_status == "bad":
                self.feedback_label.configure(text=self.detector.feedback_text, foreground="red")
            else:
                self.feedback_label.configure(text="")
                
        # Schedule the next update
        if self.is_updating:
            self.root.after(30, self.update_video)
    
    def toggle_detection(self):
        if not self.detector.running:
            # Start detection
            self.detector.start()
            self.start_stop_btn.configure(text="Stop")
            self.is_updating = True
            self.update_video()
        else:
            # Stop detection
            self.detector.stop()
            self.start_stop_btn.configure(text="Start")
            self.is_updating = False
    
    def change_exercise(self, event=None):
        self.detector.exercise_type = self.exercise_var.get()
        
    def on_closing(self):
        if self.detector.running:
            self.detector.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ExerciseGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
