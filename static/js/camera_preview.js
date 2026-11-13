(() => {
  const video = document.getElementById("identity-camera-preview");
  const placeholder = document.getElementById("identity-camera-placeholder");
  const start = document.getElementById("identity-camera-start");
  const stop = document.getElementById("identity-camera-stop");
  const status = document.getElementById("identity-camera-status");
  if (!video || !start || !stop || !status) return;

  let stream = null;

  const stopPreview = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
    video.srcObject = null;
    video.hidden = true;
    placeholder.hidden = false;
    start.disabled = false;
    stop.disabled = true;
  };

  start.addEventListener("click", async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      status.textContent = "Camera preview is unavailable in this browser or context. Continue with the approved manual process.";
      return;
    }
    start.disabled = true;
    status.textContent = "Requesting camera permission. No image capture or upload will occur.";
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false
      });
      video.srcObject = stream;
      video.hidden = false;
      placeholder.hidden = true;
      stop.disabled = false;
      status.textContent = "Camera preview is active only. No face is being recognized, captured, transmitted or stored.";
    } catch (_error) {
      stopPreview();
      status.textContent = "Camera permission was denied or the camera is unavailable. Use the approved manual identity process.";
    }
  });

  stop.addEventListener("click", () => {
    stopPreview();
    status.textContent = "Camera preview stopped. No image was captured or stored.";
  });

  window.addEventListener("pagehide", stopPreview, { once: true });
})();
