document.addEventListener("DOMContentLoaded", function () {
  const startStopBtn = document.getElementById("startStopBtn");
  const exerciseType = document.getElementById("exerciseType");
  const angleLabel = document.getElementById("angleLabel");
  const feedbackLabel = document.getElementById("feedbackLabel");

  let isRunning = false;
  let statusInterval = null;

  // Check initial status
  fetchStatus();

  startStopBtn.addEventListener("click", function () {
    if (!isRunning) {
      startDetection();
    } else {
      stopDetection();
    }
  });

  function startDetection() {
    const exercise = exerciseType.value;

    // Show connection message while the camera starts
    document.getElementById("videoStatus").classList.remove("hidden");

    // Get the video feed element
    const videoFeed = document.getElementById("videoFeed");

    // Force reload of the video feed by adding a timestamp
    const timestamp = new Date().getTime();
    videoFeed.src = `/video_feed?t=${timestamp}`;

    // Log the video feed status
    console.log("Video feed source updated:", videoFeed.src);

    // Add event listeners to detect if video feed loads or fails
    videoFeed.onload = function () {
      console.log("Video feed loaded successfully");
      // Hide connecting message once video is loaded
      document.getElementById("videoStatus").classList.add("hidden");
    };

    videoFeed.onerror = function () {
      console.error("Error loading video feed");
      // Try reloading after a short delay
      setTimeout(() => {
        videoFeed.src = `/video_feed?t=${new Date().getTime()}`;
      }, 2000);
    };

    fetch("/start", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        exercise_type: exercise,
      }),
    })
      .then((response) => response.json())
      .then((data) => {
        console.log("Success:", data);
        isRunning = true;
        startStopBtn.innerText = "Stop";
        startStopBtn.classList.add("stop");

        // Hide the connection message once detection starts
        setTimeout(() => {
          document.getElementById("videoStatus").classList.add("hidden");
        }, 1500);

        // Start polling for status updates
        if (statusInterval) clearInterval(statusInterval);
        statusInterval = setInterval(fetchStatus, 500);
      })
      .catch((error) => {
        console.error("Error:", error);
      });
  }

  function stopDetection() {
    fetch("/stop", {
      method: "POST",
    })
      .then((response) => response.json())
      .then((data) => {
        console.log("Success:", data);
        isRunning = false;
        startStopBtn.innerText = "Start";
        startStopBtn.classList.remove("stop");

        // Stop polling for status
        if (statusInterval) {
          clearInterval(statusInterval);
          statusInterval = null;
        }

        // Show connecting message when camera is stopped
        document.getElementById("videoStatus").classList.remove("hidden");
        document.getElementById("videoStatus").innerText = "Camera stopped";
      })
      .catch((error) => {
        console.error("Error:", error);
      });
  }

  function fetchStatus() {
    fetch("/status")
      .then((response) => response.json())
      .then((data) => {
        isRunning = data.running;

        if (isRunning) {
          startStopBtn.innerText = "Stop";
          startStopBtn.classList.add("stop");

          // Update status displays
          angleLabel.innerText = data.angle || "Angle: Not detected";

          if (data.form_status === "good") {
            feedbackLabel.innerText = data.feedback;
            feedbackLabel.className = "status-label good";
          } else if (data.form_status === "bad") {
            feedbackLabel.innerText = data.feedback;
            feedbackLabel.className = "status-label bad";
          } else {
            feedbackLabel.innerText = "";
            feedbackLabel.className = "status-label";
          }
        } else {
          startStopBtn.innerText = "Start";
          startStopBtn.classList.remove("stop");
        }
      })
      .catch((error) => {
        console.error("Error:", error);
      });
  }
});
