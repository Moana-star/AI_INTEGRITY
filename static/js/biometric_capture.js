(() => {
  const video = document.getElementById("biometric-camera");
  const canvas = document.getElementById("biometric-canvas");
  const start = document.getElementById("biometric-camera-start");
  const stop = document.getElementById("biometric-camera-stop");
  const submit = document.getElementById("biometric-capture-verify");
  const candidate = document.getElementById("biometric-candidate");
  const status = document.getElementById("biometric-camera-status");
  const placeholder = document.getElementById("biometric-camera-placeholder");
  const csrf = document.getElementById("biometric-csrf");
  if (!video || !start || !submit) return;

  let stream = null;
  const setStatus = (message) => { status.textContent = message; };

  start.addEventListener("click", async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("This browser or connection does not support secure camera access.");
      }
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      video.srcObject = stream;
      video.hidden = false;
      placeholder.hidden = true;
      stop.disabled = false;
      submit.disabled = false;
      start.disabled = true;
      setStatus("Camera ready. Select the candidate whose identity is being checked.");
    } catch (error) {
      setStatus(error.message || "Camera access was not granted. Use manual identity review.");
    }
  });

  stop.addEventListener("click", () => {
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    video.srcObject = null;
    video.hidden = true;
    placeholder.hidden = false;
    stop.disabled = true;
    submit.disabled = true;
    start.disabled = false;
    setStatus("Camera stopped. No image was uploaded.");
  });

  submit.addEventListener("click", async () => {
    if (!stream || !candidate.value) {
      setStatus("Start the camera and select an eligible candidate first.");
      return;
    }
    submit.disabled = true;
    setStatus("Capturing one frame and requesting provider verification…");
    try {
      const width = video.videoWidth;
      const height = video.videoHeight;
      if (!width || !height) throw new Error("Camera image is not ready. Try again.");
      canvas.width = width;
      canvas.height = height;
      canvas.getContext("2d").drawImage(video, 0, 0, width, height);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", 0.88));
      if (!blob) throw new Error("Could not capture an image from the camera.");
      const form = new FormData();
      form.append("capture", blob, "live-capture.jpg");
      form.append("csrf_token", csrf.value);
      const response = await fetch(
        "/biometric/sessions/" + encodeURIComponent(location.pathname.split("/").filter(Boolean).pop()) +
          "/students/" + encodeURIComponent(candidate.value) + "/verify",
        { method: "POST", body: form, headers: { "X-CSRFToken": csrf.value }, credentials: "same-origin" }
      );
      if (response.redirected && response.ok) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) {
        const message = response.status === 503
          ? "Live biometric verification is not configured or institutionally approved yet. No attendance was recorded."
          : "Verification was not completed (" + response.status + "). No attendance was recorded; use manual review.";
        setStatus(message);
        submit.disabled = false;
        return;
      }
      window.location.reload();
    } catch (error) {
      setStatus(error.message || "Verification failed. No attendance was recorded.");
      submit.disabled = false;
    }
  });

  window.addEventListener("pagehide", () => {
    if (stream) stream.getTracks().forEach(track => track.stop());
  });
})();