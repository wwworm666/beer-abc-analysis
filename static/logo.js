/* ===== kultura.os — Typewriter Logo ===== */
(function () {
    var FULL_TEXT = 'kultura.os';
    var CHAR_DELAY = 80;   // ms per character
    var START_DELAY = 300; // ms before typing starts
    var SESSION_KEY = 'kultura_logo_typed';

    function initLogo() {
        var logos = document.querySelectorAll('.site-logo, .header-bar-logo, .sidebar-brand');
        if (!logos.length) return;

        var alreadyTyped = sessionStorage.getItem(SESSION_KEY);

        logos.forEach(function (logo) {
            var textEl = logo.querySelector('.logo-text');
            if (!textEl) return;

            if (alreadyTyped) {
                textEl.textContent = FULL_TEXT;
                return;
            }

            // Typewriter effect
            logo.classList.add('typing');
            textEl.textContent = '';
            var i = 0;

            setTimeout(function () {
                var timer = setInterval(function () {
                    textEl.textContent = FULL_TEXT.slice(0, i + 1);
                    i++;
                    if (i >= FULL_TEXT.length) {
                        clearInterval(timer);
                        logo.classList.remove('typing');
                        sessionStorage.setItem(SESSION_KEY, '1');
                    }
                }, CHAR_DELAY);
            }, START_DELAY);
        });
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLogo);
    } else {
        initLogo();
    }
})();
