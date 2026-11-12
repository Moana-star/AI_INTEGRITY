(() => {
  "use strict";

  const attachToken = (form) => {
    if (!(form instanceof HTMLFormElement)) return;
    if (!["post", "put", "patch", "delete"].includes((form.method || "get").toLowerCase())) return;
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta || !meta.content) return;
    let field = form.querySelector('input[name="csrf_token"]');
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = "csrf_token";
      form.appendChild(field);
    }
    field.value = meta.content;
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("form").forEach(attachToken);
  });

  // Capture also covers forms inserted dynamically after the initial page render.
  document.addEventListener("submit", (event) => {
    attachToken(event.target);
  }, true);
})();
