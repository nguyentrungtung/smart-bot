import { io } from "socket.io-client";

const MAX_AUTH_RETRIES = 3;

class SocketService {
    constructor() {
        this.socket = null;
        this.handlers = new Map();  // Only data events — NOT connect/disconnect
        this.accessToken = localStorage.getItem("sb_access_token");
        this.refreshToken = localStorage.getItem("sb_refresh_token");
        this._authFailCount = 0;
        this._retrying = false;
        this._intentionalDisconnect = false;

        // Lifecycle callbacks — set by App component, called on connect/disconnect.
        // Using direct callbacks (not the handlers Map) so each socket instance
        // gets its own fresh handler, preventing the stale-flag problem where
        // the same function reference is shared across socket instances.
        this.onConnect = null;
        this.onDisconnect = null;
    }

    setTokens(access, refresh) {
        this.accessToken = access;
        if (refresh) this.refreshToken = refresh;
        localStorage.setItem("sb_access_token", access);
        if (refresh) localStorage.setItem("sb_refresh_token", refresh);
    }

    clearTokens() {
        this.accessToken = null;
        this.refreshToken = null;
        localStorage.removeItem("sb_access_token");
        localStorage.removeItem("sb_refresh_token");
    }

    async refresh() {
        if (!this.refreshToken) {
            console.warn("[SocketService] No refresh token available");
            this.clearTokens();
            return false;
        }

        const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
        try {
            const response = await fetch(`${url}/api/v1/auth/refresh`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh_token: this.refreshToken })
            });

            if (response.status === 200) {
                const result = await response.json();
                this.setTokens(result.data.access_token);
                console.log("[SocketService] Access token refreshed successfully");
                return true;
            } else {
                console.error("[SocketService] Token refresh failed:", response.status);
                this.clearTokens();
                return false;
            }
        } catch (err) {
            console.error("[SocketService] Refresh request error:", err);
            this.clearTokens();
            return false;
        }
    }

    connect(token = null) {
        if (token) {
            this.setTokens(token);
            this._authFailCount = 0;
            this._retrying = false;
        }

        if (this.socket) return;

        if (!this.accessToken) {
            console.warn("[SocketService] No access token — waiting for JWT from parent page.");
            return;
        }

        const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

        this.socket = io(url, {
            auth: { token: this.accessToken },
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
        });

        // ── Lifecycle events: registered DIRECTLY on this socket instance.
        // NOT stored in the handlers Map, so each new socket gets its own
        // fresh closures — prevents the cross-socket flag-sharing bug.

        this.socket.on("connect", () => {
            console.log("[SocketService] Connected to Smart-Bot Backend");
            this._authFailCount = 0;
            this._retrying = false;
            if (this.onConnect) this.onConnect();
        });

        this.socket.on("disconnect", (reason) => {
            if (this._intentionalDisconnect) {
                // We triggered this disconnect (new session, etc.) — not an error
                this._intentionalDisconnect = false;
                console.log("[SocketService] Intentional disconnect — no error");
                return;
            }
            console.error("[SocketService] Unexpected disconnect:", reason);
            if (this.onDisconnect) this.onDisconnect(reason);
        });

        this.socket.on("connect_error", async (err) => {
            console.error(`[SocketService] Auth failure #${this._authFailCount + 1}/${MAX_AUTH_RETRIES}: ${err.message}`);

            const isAuthError = (
                err.message.includes("Expired") ||
                err.message.includes("Invalid") ||
                err.message.includes("rejected") ||
                err.message.includes("revoked") ||
                err.message.includes("blacklisted") ||
                err.message.includes("401") ||
                err.message.includes("Unauthorized")
            );
            if (!isAuthError) return;  // Network error — let Socket.IO retry naturally

            if (this._retrying) return;  // Prevent overlapping refresh loops

            this._authFailCount++;

            if (this._authFailCount >= MAX_AUTH_RETRIES) {
                console.error(`[SocketService] Max auth retries (${MAX_AUTH_RETRIES}) reached. Re-login required.`);
                this.clearTokens();
                if (this.onAuthFailure) this.onAuthFailure();
                return;
            }

            console.log(`[SocketService] Attempting token refresh (attempt ${this._authFailCount})...`);
            this._retrying = true;
            this.disconnect(true);  // intentional — don't show auth error UI

            const refreshed = await this.refresh();
            this._retrying = false;

            if (refreshed) {
                console.log("[SocketService] Token refreshed. Reconnecting...");
                this.connect();
            } else {
                console.error("[SocketService] Refresh failed. Both tokens expired.");
                if (this.onAuthFailure) this.onAuthFailure();
            }
        });

        // ── Data event handlers: from Map — these persist across reconnects.
        this.handlers.forEach((handler, event) => {
            this.socket.on(event, handler);
        });
    }

    on(event, handler) {
        // Only data events should go through the Map.
        // connect/disconnect are lifecycle events managed via onConnect/onDisconnect callbacks.
        this.handlers.set(event, handler);
        if (this.socket) {
            this.socket.on(event, handler);
        }
    }

    emit(event, data) {
        if (this.socket) {
            this.socket.emit(event, data);
        }
    }

    disconnect(intentional = false) {
        this._intentionalDisconnect = intentional;
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
    }
}

export const socketService = new SocketService();
