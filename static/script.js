document.addEventListener("DOMContentLoaded", function () {
    const startBtn = document.getElementById("start-btn");
    const stopBtn = document.getElementById("stop-btn");
    const videoStream = document.getElementById("video-stream");
    const summaryContent = document.getElementById("summary-content");
    let updateInterval;
    let stream;
    let canvas = document.createElement("canvas");
    canvas.width = 640;  // Reduced resolution
    canvas.height = 480;

    async function initializeServerCamera() {
        try {
            videoStream.src = "/video_feed?t=" + Date.now();
            await new Promise((resolve) => {
                videoStream.onload = resolve;
                videoStream.onerror = () => {
                    throw new Error("Server webcam not accessible.");
                };
                setTimeout(resolve, 1000);
            });
            return true;
        } catch (error) {
            console.error("Server camera failed:", error);
            alert(error.message);
            return false;
        }
    }

    async function startWebcam() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480, frameRate: 15 }  // Optimized constraints
            });
            videoStream.srcObject = stream;
            return true;
        } catch (error) {
            console.error("Client webcam failed:", error);
            alert("Error: Could not access client webcam.");
            return false;
        }
    }

    startBtn.addEventListener("click", async function () {
        try {
            startBtn.disabled = true;
            const response = await fetch("/start_session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });
            if (!response.ok) throw new Error("Network response was not ok");
            const data = await response.json();

            if (data.success) {
                const useClientWebcam = confirm("Use client webcam? (Yes for client, No for server)");
                if (useClientWebcam) {
                    if (await startWebcam()) {
                        stopBtn.disabled = false;
                        updateInterval = setInterval(async () => {
                            try {
                                const ctx = canvas.getContext("2d");
                                ctx.drawImage(videoStream, 0, 0, canvas.width, canvas.height);
                                const imageData = canvas.toDataURL("image/jpeg", 0.85);  // Higher quality

                                const predictResponse = await fetch("/predict_emotion", {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ image: imageData }),
                                });
                                if (!predictResponse.ok) throw new Error("Failed to predict");
                                const summary = await predictResponse.json();
                                updateSummaryDisplay(summary);
                            } catch (error) {
                                console.error("Emotion detection failed:", error);
                            }
                        }, 2000);  // Slower update rate
                    } else {
                        throw new Error("Client webcam failed");
                    }
                } else {
                    if (await initializeServerCamera()) {
                        stopBtn.disabled = false;
                        updateInterval = setInterval(async () => {
                            try {
                                const summaryResponse = await fetch("/get_emotion_summary");
                                if (!summaryResponse.ok) throw new Error("Failed to fetch summary");
                                const summary = await summaryResponse.json();
                                updateSummaryDisplay(summary);
                            } catch (error) {
                                console.error("Summary update failed:", error);
                            }
                        }, 2000);
                    } else {
                        throw new Error("Server camera failed");
                    }
                }
            } else {
                throw new Error(data.message || "Failed to start session");
            }
        } catch (error) {
            console.error("Start session error:", error);
            alert(`Error: ${error.message}`);
            startBtn.disabled = false;
        }
    });

    stopBtn.addEventListener("click", async function () {
        try {
            clearInterval(updateInterval);
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
                videoStream.srcObject = null;
            } else {
                videoStream.src = "";
            }
            startBtn.disabled = false;
            stopBtn.disabled = true;
            summaryContent.innerHTML = "<p>No active session</p>";
            const response = await fetch("/stop_session", { method: "POST" });
            if (!response.ok) throw new Error("Failed to stop session");
        } catch (error) {
            console.error("Stop session error:", error);
            alert(`Error: ${error.message}`);
        }
    });

    function updateSummaryDisplay(summary) {
        let html = `<p>Detected Faces: ${summary.total_faces}</p><ul>`;
        if (summary.total_faces > 0) {
            for (const [emotion, count] of Object.entries(summary.emotions)) {
                html += `<li>${emotion}: ${count}</li>`;
            }
        } else {
            html += "<li>No faces detected</li>";
        }
        summaryContent.innerHTML = html + "</ul>";
    }
});