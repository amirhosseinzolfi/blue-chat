// Wait for the DOM to load
document.addEventListener("DOMContentLoaded", function () {
  // Try to find the element containing "built with chainlit"
  // This selector may need adjustment if UI changes
  const observer = new MutationObserver(() => {
    const el = Array.from(document.querySelectorAll("div,span,p,footer"))
      .find(e => e.textContent && e.textContent.trim().toLowerCase().includes("built with chainlit"));
    if (el) {
      el.textContent = "توسعه داده شده توسط بلو";
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
});
