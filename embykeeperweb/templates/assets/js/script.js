(function() {
  "use strict"; // Start of use strict

  var mainNav = document.querySelector('#mainNav');

  if (mainNav) {

    // Collapse Navbar
    var collapseNavbar = function() {

      var scrollTop = (window.pageYOffset !== undefined) ? window.pageYOffset : (document.documentElement || document.body.parentNode || document.body).scrollTop;

      if (scrollTop > 100) {
        mainNav.classList.add("navbar-shrink");
      } else {
        mainNav.classList.remove("navbar-shrink");
      }
    };
    // Collapse now if page is not at top
    collapseNavbar();
    // Collapse the navbar when page is scrolled
    document.addEventListener("scroll", collapseNavbar);
  }

  // Check if page is loaded in iframe and on Hugging Face space
  function isHuggingFaceSpace() {
    try {
      return window.self !== window.top &&
             window.location.href.includes('huggingface.co/spaces/');
    } catch (e) {
      return false;
    }
  }

  function createOverlay() {
    const currentUrl = window.location.href;
    const parts = currentUrl.replace('huggingface.co/spaces/', '').split('/');
    const redirectUrl = `https://${parts[0]}-${parts[1]}.hf.space`;

    const overlay = document.createElement('div');
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.9);
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 9999;
      cursor: pointer;
    `;

    const message = document.createElement('div');
    message.style.cssText = `
      color: white;
      font-size: 18px;
      text-align: center;
      padding: 20px;
    `;
    message.innerHTML = `Embykeeper 已启动, 您需要打开 ${redirectUrl} (点此复制) 以继续`;

    overlay.appendChild(message);
    document.body.appendChild(overlay);

    overlay.addEventListener('click', () => {
      navigator.clipboard.writeText(redirectUrl)
        .then(() => {
          const toast = document.createElement('div');
          toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 10px 20px;
            border-radius: 4px;
            font-size: 14px;
            z-index: 10000;
          `;
          toast.textContent = '网址已复制到剪贴板';
          document.body.appendChild(toast);

          setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.5s ease';
            setTimeout(() => document.body.removeChild(toast), 500);
          }, 2000);
        })
        .catch(err => {
          console.error('复制失败:', err);
        });
    });
  }

  if (isHuggingFaceSpace()) {
    createOverlay();
  }

})(); // End of use strict
