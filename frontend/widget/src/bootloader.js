(function () {
    // Smart-Bot Bootloader
    // This script is intended to be included in any parent website.
    // It injects the chat widget iframe and handles its lifecycle.

    const WIDGET_URL = "http://localhost:5173"; // Change to production URL
    const WIDGET_ID = "smart-bot-widget-container";

    function init() {
        if (document.getElementById(WIDGET_ID)) return;

        // 1. Create Container
        const container = document.createElement('div');
        container.id = WIDGET_ID;
        container.style.position = 'fixed';
        container.style.bottom = '20px';
        container.style.right = '20px';
        container.style.zIndex = '999999';
        container.style.width = '80px';
        container.style.height = '80px';
        container.style.transition = 'all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
        container.style.overflow = 'hidden';
        container.style.borderRadius = '50%'; // Initial state is the bubble

        // 2. Create Iframe
        const iframe = document.createElement('iframe');
        iframe.src = WIDGET_URL;
        iframe.style.width = '100%';
        iframe.style.height = '100%';
        iframe.style.border = 'none';
        iframe.style.background = 'transparent';
        iframe.allow = "microphone"; // Allow voice recording

        container.appendChild(iframe);
        document.body.appendChild(container);

        // 3. Setup postMessage Communication
        window.addEventListener('message', (event) => {
            // SECURITY: Ensure message is from our widget
            if (event.origin !== WIDGET_URL) return;

            const data = event.data;

            // Handle Dynamic Resizing
            if (data.type === 'SMART_BOT_RESIZE') {
                const { width, height } = data;
                container.style.width = width + 'px';
                container.style.height = height + 'px';

                // If height > 100, we're likely in "expanded" mode
                if (height > 100) {
                    container.style.borderRadius = '16px';
                } else {
                    container.style.borderRadius = '50%';
                }
            }
        });

        // 4. Inject Mock Auth Token for Demo purposes 
        // In production, the parent site would handle this
        setTimeout(() => {
            iframe.contentWindow.postMessage({
                type: 'SMART_BOT_AUTH',
                token: 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.e30.dummy'
            }, WIDGET_URL);
        }, 2000);
    }

    if (document.readyState === 'complete') {
        init();
    } else {
        window.addEventListener('load', init);
    }
})();
