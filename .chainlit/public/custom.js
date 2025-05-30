// Wait for the DOM to load
document.addEventListener("DOMContentLoaded", function () {
  // Try to find the element containing "built with chainlit"
  // This selector may need adjustment if UI changes
  const observer = new MutationObserver(() => {
    const el = Array.from(document.querySelectorAll("div,span,p,footer"))
      .find(e => e.textContent && e.textContent.trim().toLowerCase().includes("built with chainlit"));
    if (el) {
      el.textContent = "توسعه داده شده توسط بلو";
      el.style.direction = "rtl";
      el.style.textAlign = "right";
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  
  // Function to apply RTL adjustments to dynamic elements
  function applyRTLAdjustments() {
    // Fix RTL for thread history items
    const threadHistoryItems = document.querySelectorAll('[data-testid="thread-history-sidebar"] .line-clamp-2');
    threadHistoryItems.forEach(item => {
      item.style.direction = 'rtl';
      item.style.textAlign = 'right';
      item.style.fontFamily = "'Vazirmatn', 'IRANSans', sans-serif";
    });

    // Fix RTL for chat input placeholder
    const chatInput = document.querySelector('[data-testid="chat-input"] textarea');
    if (chatInput) {
      chatInput.style.direction = 'rtl';
      chatInput.style.textAlign = 'right';
      chatInput.style.fontFamily = "'Vazirmatn', 'IRANSans', sans-serif";
    }
    
    // Fix RTL for chat history search input
    const searchInput = document.querySelector('[data-cmdk-input]');
    if (searchInput) {
      searchInput.style.direction = 'rtl';
      searchInput.style.textAlign = 'right';
      searchInput.style.fontFamily = "'Vazirmatn', 'IRANSans', sans-serif";
      searchInput.style.paddingRight = '12px';
    }
  }

  // Apply RTL adjustments periodically to catch dynamic elements
  setTimeout(applyRTLAdjustments, 500);
  setInterval(applyRTLAdjustments, 2000);
});
