import { useState, useEffect, useRef } from 'preact/hooks';

import { MessageCircle, X, Maximize2, Minimize2, RefreshCcw } from 'lucide-preact';
import { socketService } from './services/socket';
import { iframeSync } from './services/iframeSync';
import { MessageList } from './components/MessageList';
import { InputArea } from './components/InputArea';
import { ThoughtStream } from './components/ThoughtStream';
import './app.css';

export function App() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [currentThought, setCurrentThought] = useState("");
  const [partialResponse, setPartialResponse] = useState("");
  const partialRef = useRef(""); // Latest value for the complete callback
  const thoughtRef = useRef(""); // Accumulates thought chunks as one string
  const [pendingMetadata, setPendingMetadata] = useState(null);
  const metadataRef = useRef(null);
  const initializingRef = useRef(false);



  const [session_id, setSessionId] = useState(() => {
    const saved = localStorage.getItem("smart_bot_session_id");
    return saved || null; // Return null initially if missing, fetch it below
  });

  const [authError, setAuthError] = useState(false);
  const [capabilities, setCapabilities] = useState({ vision: false, audio: false });

  // Helper: request a new server-side session. Re-fetches token on 401 via socketService.refresh()
  const ensureSession = async (oldSessionId = null) => {
    if (!oldSessionId && (localStorage.getItem("smart_bot_session_id") || initializingRef.current)) return;
    initializingRef.current = true;
    const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

    const fetchSession = async () => {
      const options = {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${socketService.accessToken}`
        }
      };
      if (oldSessionId) {
        options.body = JSON.stringify({ old_session_id: oldSessionId });
      }
      return await fetch(`${url}/api/v1/chat/new-session`, options);
    };

    try {
      console.log("[Auth] Requesting new server-side session...");
      let resp = await fetchSession();
      
      if (resp.status === 401 || resp.status === 403) {
        console.warn("[Auth] Token expired during ensureSession, trying refresh...");
        const refreshed = await socketService.refresh();
        if (refreshed) {
          resp = await fetchSession(); // retry
        } else {
          console.error("[Auth] EnsureSession refresh failed.");
          if (socketService.onAuthFailure) socketService.onAuthFailure();
          return;
        }
      }

      if (resp.ok) {
        const r = await resp.json();
        setSessionId(r.data.session_id);
        localStorage.setItem("smart_bot_session_id", r.data.session_id);
        console.log("[Auth] Session acquired:", r.data.session_id);
      } else {
        console.warn("[Auth] Session request failed:", resp.status);
        setAuthError(true);
      }
    } catch (err) {
      console.error("[Auth] ensureSession error:", err);
    } finally {
      initializingRef.current = false;
    }
  };

  useEffect(() => {
    // 1. Start reporting height to parent for dynamic resize
    iframeSync.startResizing();

    // 2. Socket lifecycle callbacks — direct callbacks (not handlers Map) so each
    //    socket instance gets fresh closures with no cross-socket flag sharing.
    socketService.onConnect = async () => {
      console.log("[App] Socket connected — clearing auth error");
      setAuthError(false);
      await ensureSession();
    };


    socketService.onDisconnect = (reason) => {
      console.error("[App] Unexpected socket disconnect:", reason);
      setAuthError(true);
      setMessages((prev) => [...prev, {
        sender: 'bot',
        text: `⚠️ Kết nối bị mất: ${reason}. Vui lòng tải lại trang.`
      }]);
      setLoading(false);
    };

    socketService.onAuthFailure = () => {
      setAuthError(true);
      setMessages((prev) => [...prev, {
        sender: 'bot',
        text: "⚠️ Phiên đăng nhập hết hạn. Vui lòng tải lại trang hoặc đăng nhập lại."
      }]);
    };

    // Listen for auth tokens from parent site (iframe embed mode — primary auth path)
    iframeSync.listenForEvents(async (type, payload) => {
      if (type === "auth") {
        console.log("[Auth] Received JWT via postMessage from parent page");
        setAuthError(false);
        socketService.connect(payload);  // Passes new token, resets fail counter
      }
    });

    // First-load: connect if token already cached in localStorage (returning user)
    const initializeAuthAndSession = async () => {
      if (!socketService.accessToken) {
        console.warn("[Auth] No access token on load. Waiting for JWT from parent page.");
        return;
      }
      console.log("[Auth] Cached access token found. Connecting...");
      socketService.connect();
    };

    initializeAuthAndSession();

    socketService.on("message_stream", (data) => {
      console.log("FE Debug: Received message_stream chunk:", data.chunk);
      partialRef.current += data.chunk;
      setPartialResponse(partialRef.current);
      setLoading(false);
    });

    socketService.on("thought_stream", (data) => {
      console.log("FE Debug: Received thought_stream:", data.content);
      thoughtRef.current += data.content;
      setCurrentThought(thoughtRef.current);
      setLoading(false);
    });

    socketService.on("message_complete", () => {
      console.log("FE Debug: Stream complete. Finalizing message:", partialRef.current);
      if (partialRef.current || thoughtRef.current) {
        const finalContent = partialRef.current;
        const finalThinking = thoughtRef.current;
        const interaction_id = metadataRef.current?.interaction_id || null;

        setMessages((prev) => [...prev, {
          sender: 'bot',
          text: finalContent,
          thinking: finalThinking || null,
          interaction_id: interaction_id,
          rated: null
        }]);
      }
      partialRef.current = "";
      thoughtRef.current = "";
      setPartialResponse("");
      setLoading(false);
      setCurrentThought("");
      setPendingMetadata(null);
      metadataRef.current = null;
    });

    socketService.on("message_metadata", (data) => {
      console.log("FE Debug: Received message_metadata:", data);
      setPendingMetadata(data);
      metadataRef.current = data;
    });

    // Listen for multimodal capabilities from backend
    socketService.on("multimodal_config", (config) => {
      console.log("FE Debug: Received multimodal_config:", config);
      setCapabilities(config);
    });

    // NOTE: connect/disconnect lifecycle events are handled via
    // socketService.onConnect / socketService.onDisconnect direct callbacks
    // (set at lines 38-51 above). Do NOT register them via socketService.on()
    // — that would re-add them to the handlers Map and cause double-handler
    // registration on every new socket instance.

    socketService.on("error", (data) => {
      console.error("FE Debug: Received error event from backend:", data);
      setMessages((prev) => [...prev, {
        sender: 'bot',
        text: `⚠️ Ops! ${data.message || "Đã có lỗi xảy ra."} (Mã code: ${data.code || "unknown"})`
      }]);
      setLoading(false);
    });

    // Handle incoming audio for TTS
    socketService.on("audio_chunk", (data) => {
      const blob = new Blob([data.buffer], { type: 'audio/mp3' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play().catch(e => console.error("TTS Playback failed:", e));
    });


    // Intentional disconnect on unmount — prevents the onDisconnect callback
    // from firing with authError=true during hot-reload / Strict Mode double invocations.
    return () => socketService.disconnect(true);
  }, []);

  // Helper: convert Blob to base64 data URL with timeout protection
  const blobToBase64 = (blob, timeout = 30000) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      const timer = setTimeout(() => {
        reader.abort();
        reject(new Error(`Base64 conversion timeout after ${timeout}ms`));
      }, timeout);

      reader.onloadend = () => {
        clearTimeout(timer);
        resolve(reader.result);
      };
      reader.onerror = (err) => {
        clearTimeout(timer);
        reject(err || new Error("FileReader error"));
      };
      reader.readAsDataURL(blob);
    });
  };

  const handleSendMessage = async (text, attachments = {}) => {
    const localAudioUrl = (attachments.audio && attachments.audio instanceof Blob) ? URL.createObjectURL(attachments.audio) : null;
    const userMsg = {
      sender: 'user',
      text: text || (attachments.audio ? "🎤 Audio message" : "📸 Image message"),
      attachments,
      localAudioUrl
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    // Build payload with proper format for backend
    const payload = {
      session_id,
      content: text,
    };

    // Add image as data URL string (already base64 from FileReader)
    if (attachments.image) {
      payload.image = attachments.image;
      console.log("FE Debug: Attaching image to payload, length:", attachments.image.length);
    }

    // Convert audio Blob to base64 data URL before sending
    if (attachments.audio && attachments.audio instanceof Blob) {
      try {
        // Pre-check: warn if audio blob is suspiciously large (>50MB raw = ~66MB base64)
        const audioMB = (attachments.audio.size / 1024 / 1024).toFixed(2);
        if (attachments.audio.size > 50 * 1024 * 1024) {
          throw new Error(`Audio quá lớn: ${audioMB}MB (max 50MB)`);
        }

        // Convert with 60s timeout (handles very large files on slow networks)
        const audioBase64 = await blobToBase64(attachments.audio, 60000);
        const base64MB = (audioBase64.length / 1024 / 1024).toFixed(2);

        payload.audio = audioBase64;
        console.log("FE Debug: Audio converted, base64 size:", base64MB, "MB (raw was", audioMB, "MB)");
      } catch (err) {
        console.error("FE Error: Audio processing failed:", err.message);
        setMessages((prev) => [...prev, {
          sender: 'bot',
          text: `❌ Lỗi xử lý âm thanh: ${err.message}`
        }]);
        setLoading(false);
        return;  // Stop sending if audio processing fails
      }
    }

    if (!session_id) {
      console.warn("FE Debug: Attempted to send message without session_id. Re-initializing...");
      // Try to re-initialize session if it's missing
      const url = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
      try {
        const sessionResp = await fetch(`${url}/api/v1/chat/new-session`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${socketService.accessToken}`
          }
        });
        if (sessionResp.ok) {
          const sResult = await sessionResp.json();
          setSessionId(sResult.data.session_id);
          localStorage.setItem("smart_bot_session_id", sResult.data.session_id);
          payload.session_id = sResult.data.session_id; // Update payload with new ID
          console.log("FE Debug: Emergency session acquired:", sResult.data.session_id);
        } else {
          setMessages((prev) => [...prev, {
            sender: 'bot',
            text: "❌ Lỗi khởi tạo phiên làm việc. Vui lòng tải lại trang."
          }]);
          setLoading(false);
          return;
        }
      } catch (err) {
        console.error("FE Error: Emergency session failed:", err);
        setLoading(false);
        return;
      }
    }

    if (!socketService.socket?.connected) {
      setMessages((prev) => [...prev, {
        sender: 'bot',
        text: "🚫 Unable to send. Please refresh or authenticate again."
      }]);
      setLoading(false);
      return;
    }

    socketService.emit("message", payload);
  };

  const handleRateMessage = (interaction_id, rating) => {
    console.log(`FE Debug: Rating interaction ${interaction_id} as ${rating}`);
    socketService.emit("message_rate", { interaction_id, rating });

    // Update local state to show it was rated
    setMessages((prev) => prev.map(m =>
      m.interaction_id === interaction_id ? { ...m, rated: rating } : m
    ));
  };

  useEffect(() => {
    // Expose for E2E testing
    window.testVoiceSend = handleSendMessage;
    return () => delete window.testVoiceSend;
  }, [handleSendMessage]);



  const [newSessionInProgress, setNewSessionInProgress] = useState(false);

  const handleNewSession = async () => {
    if (newSessionInProgress) return;  // Guard: prevent double-click / concurrent calls
    setNewSessionInProgress(true);

    try {
      // 1. Fetch new session explicitly via our resilient helper
      await ensureSession(session_id);
      
      console.log("Session reset success");

      // 2. Reset UI state
      setLoading(false);
      partialRef.current = "";
      thoughtRef.current = "";
      setPartialResponse("");
      setCurrentThought("");
      setPendingMetadata(null);
      metadataRef.current = null;
      setMessages([{
        sender: 'bot',
        text: "✨ Cuộc hội thoại hoàn toàn mới đã được bắt đầu. Em có thể hỗ trợ gì cho anh/chị ạ?"
      }]);

      // 3. Reconnect socket — mark as intentional so disconnect handler skips auth error.
      // onConnect will fire, but ensureSession() will skip because it just wrote to localStorage.
      socketService.disconnect(true);
      socketService.connect();
    } finally {
      setNewSessionInProgress(false);  // Always re-enable button
    }
  };


  const [isMaximized, setIsMaximized] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 400, height: 620 });
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing || isMaximized) return;

      // Since widget is bottom-right, we calculate width/height based on top-left drag
      // Find the parent distance from bottom right
      const rect = document.querySelector('.chat-window')?.getBoundingClientRect();
      if (!rect) return;

      const newWidth = Math.max(320, window.innerWidth - e.clientX - 32); // 32 is roughly the margin
      const newHeight = Math.max(400, window.innerHeight - e.clientY - 96);

      setDimensions({ width: newWidth, height: newHeight });
    };

    const handleMouseUp = () => setIsResizing(false);

    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, isMaximized]);

  useEffect(() => {
    // Notify parent about new dimensions whenever states change
    const finalWidth = isMaximized ? 'calc(100vw - 4rem)' : `${dimensions.width}px`;
    const finalHeight = isMaximized ? 'calc(100vh - 8rem)' : `${dimensions.height}px`;
    iframeSync.reportResize(finalWidth, finalHeight);
  }, [isMaximized, dimensions]);

  const toggleMaximized = (e) => {
    e.stopPropagation();
    setIsMaximized(!isMaximized);
  };

  const toggleWidget = () => setIsOpen(!isOpen);
  return (
    <div className={`widget-container ${isMaximized ? 'maximized' : ''}`}>
      {isOpen && (
        <div
          className={`chat-window ${isMaximized ? 'maximized' : ''}`}
          style={!isMaximized ? { width: `${dimensions.width}px`, height: `${dimensions.height}px` } : {}}
        >
          {/* Resize Handle - Top Left Corner */}
          {!isMaximized && (
            <div
              className="resize-handle"
              onMouseDown={(e) => {
                e.preventDefault();
                setIsResizing(true);
              }}
            />
          )}

          <div className="chat-header">
            <div
              className={`status-dot ${authError ? 'error' : ''}`}
              title={authError ? "Authentication Required" : "Connected"}
            ></div>
            <h2>Smart-Bot Advisor</h2>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.25rem' }}>
              <button
                className="icon-btn"
                onClick={handleNewSession}
                title="New Conversation"
                disabled={newSessionInProgress}
                style={newSessionInProgress ? { opacity: 0.4, cursor: 'not-allowed' } : {}}
              >
                <RefreshCcw size={18} className={newSessionInProgress ? 'spin' : ''} />
              </button>
              <button
                className="icon-btn"
                onClick={toggleMaximized}
                title={isMaximized ? "Restore" : "Maximize"}
              >
                {isMaximized ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
              </button>
              <button
                className="icon-btn"
                onClick={toggleWidget}
                title="Close"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          <MessageList
            messages={messages}
            partialResponse={partialResponse}
            onRate={handleRateMessage}
          />

          <ThoughtStream thought={currentThought} />


          <InputArea
            onSendMessage={handleSendMessage}
            msgInProgress={loading}
            capabilities={capabilities}
          />

        </div>
      )}

      <div
        className={`chat-bubble ${isOpen ? 'active' : ''}`}
        onClick={toggleWidget}
      >
        {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
      </div>
    </div>
  );
}
