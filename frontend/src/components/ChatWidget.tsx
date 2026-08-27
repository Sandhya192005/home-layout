import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { ChatMessage } from "../api/types";
import "./chat-widget.css";

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setInput("");
    setSending(true);
    setError(null);
    try {
      const { reply } = await api.chat({ messages: next });
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the chat assistant");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={`chat-widget ${open ? "chat-widget-open" : ""}`}>
      {open && (
        <div className="chat-panel card">
          <div className="chat-panel-head">
            <span>Ask about your house</span>
            <button type="button" className="chat-close" onClick={() => setOpen(false)} aria-label="Close chat">
              &times;
            </button>
          </div>
          <div className="chat-messages">
            {messages.length === 0 && (
              <p className="muted chat-empty">
                Ask anything about room sizes, Vastu, construction costs, plot setbacks, or your generated plan.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble chat-bubble-${m.role}`}>
                {m.content}
              </div>
            ))}
            {sending && <div className="chat-bubble chat-bubble-assistant chat-bubble-pending">Thinking…</div>}
          </div>
          {error && <div className="error-banner chat-error">{error}</div>}
          <form
            className="chat-input-row"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="e.g. How big should a master bedroom be?"
              disabled={sending}
            />
            <button type="submit" className="btn btn-primary" disabled={sending || !input.trim()}>
              Send
            </button>
          </form>
        </div>
      )}
      <button type="button" className="chat-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "Close" : "Ask about your house"}
      </button>
    </div>
  );
}
