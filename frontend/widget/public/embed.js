(function (w, d, s, o, f) {
    /**
     * Google Analytics / Intercom style bootloader logic.
     * Supports initialization via command queue: smartbot('init', { token: '...' })
     */
    const SCRIPT_URL = f;
    const BASE_URL = SCRIPT_URL.substring(0, SCRIPT_URL.lastIndexOf('/'));

    const initWidget = (config = {}) => {
        if (d.getElementById('smart-bot-container')) return;

        const container = d.createElement('div');
        container.id = 'smart-bot-container';
        Object.assign(container.style, {
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            zIndex: '2147483647',
            width: '80px',
            height: '80px',
            borderRadius: '50%',
            boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
            overflow: 'hidden',
            transition: 'all 0.4s cubic-bezier(0.18, 0.89, 0.32, 1.28)',
            border: '1px solid rgba(0,0,0,0.05)'
        });

        const iframe = d.createElement('iframe');
        iframe.id = 'smart-bot-iframe';
        iframe.src = BASE_URL;
        iframe.title = 'Smart-Bot Advisor';
        iframe.allow = 'microphone; camera; clipboard-write;';

        Object.assign(iframe.style, {
            width: '100%',
            height: '100%',
            border: 'none',
            background: 'transparent'
        });

        container.appendChild(iframe);
        d.body.appendChild(container);

        // Sync signals (Resize only)
        w.addEventListener('message', (event) => {
            if (event.origin !== BASE_URL) return;
            if (event.data.type === 'SMART_BOT_RESIZE') {
                const { width, height } = event.data;
                container.style.width = typeof width === 'number' ? width + 'px' : width;
                container.style.height = typeof height === 'number' ? height + 'px' : height;
                if (parseInt(height) > 100) {
                    container.style.borderRadius = '18px';
                } else {
                    container.style.borderRadius = '50%';
                }
            }
        });

        // Authentication Injection
        const injectAuth = (token) => {
            if (token) {
                console.log("[Smart-Bot-Embed] Updating Token...");
                iframe.contentWindow.postMessage({ type: 'SMART_BOT_AUTH', token: token }, BASE_URL);
            }
        };

        iframe.addEventListener('load', () => {
            const token = config.token || w.SMART_BOT_TOKEN;
            setTimeout(() => injectAuth(token), 500);
        });

        // Command handler for future calls (e.g., token rotation)
        w[o] = function () {
            const args = Array.prototype.slice.call(arguments);
            if (args[0] === 'init') {
                const config = args[1] || {};
                const iframe = d.getElementById('smart-bot-iframe');
                if (iframe) {
                    // Update existing token
                    console.log("[Smart-Bot-Embed] Updating Token...");
                    iframe.contentWindow.postMessage({ type: 'SMART_BOT_AUTH', token: config.token }, BASE_URL);
                } else {
                    initWidget(config);
                }
            }
        };
    };

    // Process initial queue
    const processQueue = () => {
        const instance = w[o];
        const queue = instance ? instance.q || [] : [];
        const initCmd = queue.find(args => args[0] === 'init');
        initWidget(initCmd ? initCmd[1] : {});
    };

    if (d.readyState === 'complete') {
        processQueue();
    } else {
        w.addEventListener('load', processQueue);
    }

})(window, document, 'script', 'smartbot', document.currentScript.src);
