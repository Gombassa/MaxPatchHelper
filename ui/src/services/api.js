/**
 * API Client Services for SSE and WebSocket communication.
 * Handles FastAPI REST endpoints, SSE text/event-stream readers, and WebSocket stateful sessions.
 */

const API_URL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000/api`;

/**
 * Helper to stream SSE chunks from a POST request.
 * Returns a cancel function to abort the stream.
 */
function streamPost(url, body, { onMessage, onError, onDone }) {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || `HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const rawData = trimmed.slice(6);
            try {
              const parsed = JSON.parse(rawData);
              onMessage(parsed);
            } catch (e) {
              console.error("Failed to parse SSE JSON chunk:", rawData, e);
            }
          }
        }
      }

      // Flush any remaining data in the buffer
      if (buffer.trim().startsWith("data: ")) {
        try {
          const parsed = JSON.parse(buffer.trim().slice(6));
          onMessage(parsed);
        } catch (e) {}
      }

      onDone?.();
    } catch (error) {
      if (error.name === "AbortError") {
        onDone?.();
      } else {
        onError?.(error);
      }
    }
  })();

  return () => {
    controller.abort();
  };
}

/**
 * Connects to the Guided Build WebSocket.
 * Returns send helper methods and a close handler.
 */
export function connectGuidedWebSocket({ onMessage, onStatusChange }) {
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = import.meta.env.VITE_WS_URL || `${wsProtocol}//${window.location.hostname}:8000/api/ws/guided`;

  let socket = null;
  let reconnectTimeout = null;
  let isIntentionalClose = false;
  let retryCount = 0;
  const maxRetries = 5;

  function connect() {
    onStatusChange("connecting");
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      onStatusChange("connected");
      retryCount = 0;
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error("WebSocket message parse error:", e);
      }
    };

    socket.onerror = (err) => {
      console.error("WebSocket error:", err);
    };

    socket.onclose = () => {
      if (isIntentionalClose) {
        onStatusChange("disconnected");
        return;
      }

      onStatusChange("disconnected");
      if (retryCount < maxRetries) {
        const delay = Math.min(1000 * Math.pow(2, retryCount), 10000);
        retryCount++;
        console.warn(`WebSocket disconnected. Reconnecting in ${delay}ms...`);
        reconnectTimeout = setTimeout(connect, delay);
      }
    };
  }

  connect();

  return {
    sendChat: (text) => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "chat", text }));
      } else {
        throw new Error("WebSocket connection is not active");
      }
    },
    sendGenerate: () => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "generate" }));
      } else {
        throw new Error("WebSocket connection is not active");
      }
    },
    sendExit: () => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "exit" }));
      } else {
        throw new Error("WebSocket connection is not active");
      }
    },
    close: () => {
      isIntentionalClose = true;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (socket) socket.close();
    }
  };
}

export const api = {
  /**
   * Health check endpoint
   */
  async getHealth() {
    const res = await fetch(`${API_URL}/health`);
    if (!res.ok) throw new Error("Health check failed");
    return res.json();
  },

  /**
   * Document search/retrieval
   */
  async retrieveDocs({ query, domain = null, version = "8", results = 3 }) {
    const res = await fetch(`${API_URL}/retrieve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, domain, version, results })
    });
    if (!res.ok) throw new Error("Document retrieval failed");
    return res.json();
  },

  /**
   * Direct patch validation
   */
  async validatePatch({ patch, domain = null, device_type = null }) {
    const res = await fetch(`${API_URL}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patch, domain, device_type })
    });
    if (!res.ok) throw new Error("Patch validation failed");
    return res.json();
  },

  /**
   * Explainer SSE Stream
   */
  streamExplain({ query, domain = null, version = "8" }, callbacks) {
    return streamPost(`${API_URL}/explain`, { query, domain, version }, callbacks);
  },

  /**
   * Generator SSE Stream
   */
  streamGenerate({ query, domain = null, version = "8" }, callbacks) {
    return streamPost(`${API_URL}/generate`, { query, domain, version }, callbacks);
  }
};
