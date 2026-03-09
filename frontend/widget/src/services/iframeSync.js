/**
 * Service to handle 2-way postMessage communication for iframe resizing and security.
 */
class IframeSyncService {
    constructor() {
        this.allowedOrigins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173" // Vite default dev port
        ];
    }

    /**
     * Periodically measures the widget's DOM height and broadcasts it to the parent.
     */
    startResizing(elementSelector = "#app") {
        const reportHeight = () => {
            const element = document.querySelector(elementSelector);
            if (!element) return;

            const height = element.scrollHeight;
            const width = element.scrollWidth;

            window.parent.postMessage(
                {
                    type: "SMART_BOT_RESIZE",
                    height,
                    width
                },
                "*" // In production, replace with specific domain or use parent origin tracking
            );
        };

        // Report on initial load and every 200ms for responsiveness
        reportHeight();
        setInterval(reportHeight, 200);
    }

    /**
     * Listens for messages from the parent window (e.g., Auth tokens).
     */
    listenForEvents(onEvent) {
        window.addEventListener("message", (event) => {
            // SECURITY: Strict origin check
            // For local dev, we might be more lenient, but production MUST be strict.
            if (!this.allowedOrigins.includes(event.origin) && event.origin !== "null") {
                console.warn("Blocked unrecognized postMessage origin:", event.origin);
                return;
            }

            if (event.data && event.data.type === "SMART_BOT_AUTH") {
                onEvent("auth", event.data.token);
            }
        });
    }
}

export const iframeSync = new IframeSyncService();
