// Custom JavaScript for RTL adjustments and enhancements

document.addEventListener('DOMContentLoaded', function() {
  // Function to apply RTL adjustments to dynamically added elements
  function applyRTLAdjustments() {
    // Apply RTL to chat history sidebar items 
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
    
    // Fix sidebar headings
    const sidebarHeadings = document.querySelectorAll('[data-testid="thread-history-sidebar"] [role="heading"]');
    sidebarHeadings.forEach(heading => {
      heading.style.direction = 'rtl';
      heading.style.textAlign = 'right';
      heading.style.paddingRight = '0.75rem';
      heading.style.fontFamily = "'Vazirmatn', 'IRANSans', sans-serif";
    });
    
    // Apply RTL to dialog titles and content
    const dialogTitles = document.querySelectorAll('.cl-dialog-title, [role="dialog"] h2, [role="dialog"] h3');
    dialogTitles.forEach(title => {
      title.style.direction = 'rtl';
      title.style.textAlign = 'right';
      title.style.fontFamily = "'Vazirmatn', 'IRANSans', sans-serif";
    });
  }

  // Initial application
  setTimeout(applyRTLAdjustments, 500);

  // Apply RTL adjustments periodically to catch dynamic elements
  setInterval(applyRTLAdjustments, 2000);
  
  // Replace "Powered by Chainlit" with custom text if found
  function updateWatermark() {
    const watermarkElements = document.querySelectorAll('.watermark');
    watermarkElements.forEach(el => {
      if (el.textContent.includes('Chainlit')) {
        el.textContent = 'توسعه داده شده توسط بلو';
        el.style.direction = 'rtl';
        el.style.textAlign = 'right';
      }
    });
  }

  // Apply watermark changes periodically
  setTimeout(updateWatermark, 500);
  setInterval(updateWatermark, 3000);

  // Function to enhance the loading animation experience with modern circular spinner
  function enhanceLoadingAnimations() {
    // Find any active loading messages
    const loadingMessages = document.querySelectorAll('.message-run');
    
    loadingMessages.forEach((loader, index) => {
      // Check if we've already enhanced this loader
      if (!loader.hasAttribute('data-enhanced')) {
        // Mark as enhanced to avoid duplicating
        loader.setAttribute('data-enhanced', 'true');
        loader.classList.add('modern-loading-active');
        
        // Clear any existing content in the loader
        loader.innerHTML = '';
        
        // Create modern loading container
        const loadingContainer = document.createElement('div');
        loadingContainer.className = 'modern-loading-container';
        
        // Add loading text
        const loadingText = document.createElement('span');
        loadingText.textContent = 'در حال پاسخ';
        loadingText.style.fontFamily = "'Vazirmatn', 'IRANSans', sans-serif";
        loadingText.style.fontSize = '0.9rem';
        loadingText.style.fontWeight = '400';
        
        // Add modern circular spinner
        const spinner = document.createElement('div');
        spinner.className = 'modern-loading-spinner';
        
        // Append elements to container
        loadingContainer.appendChild(loadingText);
        loadingContainer.appendChild(spinner);
        
        // Append container to loader
        loader.appendChild(loadingContainer);
        
        // Add fade-in animation
        loadingContainer.style.opacity = '0';
        loadingContainer.style.transform = 'translateY(5px)';
        loadingContainer.style.transition = 'all 0.3s ease';
        
        // Trigger animation after a brief delay
        setTimeout(() => {
          loadingContainer.style.opacity = '1';
          loadingContainer.style.transform = 'translateY(0)';
        }, 50);
      }
    });
  }

  // Add enhanceLoadingAnimations to the applyRTLAdjustments function
  function applyRTLAdjustments() {
    // ...existing code...
    
    // Apply custom animation to loading messages
    enhanceLoadingAnimations();
  }
  
  // Add a MutationObserver to watch for new loading elements
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.addedNodes.length) {
        // Check if any new loading messages were added
        const loadingElements = document.querySelectorAll('.message-run:not([data-enhanced])');
        if (loadingElements.length > 0) {
          enhanceLoadingAnimations();
        }
      }
    });
  });
  
  // Start observing the document for message container changes
  observer.observe(document.querySelector('#root') || document.body, {
    childList: true,
    subtree: true
  });
});