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
  }
};
