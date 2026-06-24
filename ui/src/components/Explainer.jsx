import React, { useState, useRef, useEffect } from 'react';
import { api } from '../services/api';
import CodeBlock from '../shared/CodeBlock';

// Helper to render inline formatting (bold, italic, inline code)
function renderInlineMarkdown(text) {
  const regex = /(\*\*.*?\*\*|\*.*?\*|`.*?`)/g;
  const parts = text.split(regex);

  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={index} className="inline-code">{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

// Custom Markdown parser returning React nodes
export function parseMarkdown(text) {
  if (!text) return null;

  const parts = text.split(/(```[\s\S]*?```)/g);

  return parts.map((part, index) => {
    if (part.startsWith('```')) {
      const match = part.match(/```(\w*)\n([\s\S]*?)```/);
      const language = match ? match[1] : 'text';
      const content = match ? match[2] : part.slice(3, -3);
      return (
        <CodeBlock 
          key={index} 
          code={content.trim()} 
          language={language || 'text'} 
          fileName={language === 'json' ? 'patch.maxpat' : 'explanation.txt'}
        />
      );
    }

    const paragraphs = part.split(/\n\n+/);
    return paragraphs.map((p, pIndex) => {
      const trimmed = p.trim();
      if (!trimmed) return null;

      // Handle Bullet lists
      if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
        const items = trimmed.split(/\n[*+-]\s+/);
        return (
          <ul key={`ul-${index}-${pIndex}`} className="markdown-list">
            {items.map((item, iIndex) => {
              const itemText = iIndex === 0 ? item.substring(2) : item;
              return <li key={iIndex}>{renderInlineMarkdown(itemText)}</li>;
            })}
          </ul>
        );
      }

      // Handle Headings
      if (trimmed.startsWith('#')) {
        const level = (trimmed.match(/^#+/) || ['#'])[0].length;
        const textContent = trimmed.replace(/^#+\s+/, '');
        const HeadingTag = `h${Math.min(level + 1, 6)}`;
        return <HeadingTag key={`h-${index}-${pIndex}`}>{renderInlineMarkdown(textContent)}</HeadingTag>;
      }

      return (
        <p key={`p-${index}-${pIndex}`} className="markdown-para">
          {renderInlineMarkdown(trimmed)}
        </p>
      );
    });
  });
}

export default function Explainer() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Welcome! Ask me any question about Cycling \'74 Max, MSP audio signals, or the Max for Live (M4L) Live Object Model. I can describe connection routing, object parameters, or help you debug patching logic.'
    }
  ]);
  const [input, setInput] = useState('');
  const [domain, setDomain] = useState('max'); // 'max' | 'm4l'
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);

  const messagesEndRef = useRef(null);
  const cancelStreamRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Clean up any active stream on unmount
  useEffect(() => {
    return () => {
      if (cancelStreamRef.current) cancelStreamRef.current();
    };
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    setError(null);
    const userMessage = input.trim();
    setInput('');

    // Append user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsStreaming(true);

    // Placeholder assistant message for streaming
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    let accumulatedContent = '';

    const cancel = api.streamExplain(
      { query: userMessage, domain: domain, version: '8' },
      {
        onMessage: (data) => {
          if (data.error) {
            setError(data.error);
            setIsStreaming(false);
            return;
          }
          if (data.token) {
            accumulatedContent += data.token;
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: 'assistant',
                content: accumulatedContent
              };
              return updated;
            });
          }
        },
        onError: (err) => {
          console.error("Explainer SSE stream error:", err);
          setError("Failed to get explanation. Please check backend status.");
          setIsStreaming(false);
        },
        onDone: () => {
          setIsStreaming(false);
        }
      }
    );

    cancelStreamRef.current = cancel;
  };

  const handleStop = (e) => {
    if (e) e.preventDefault();
    if (cancelStreamRef.current) {
      cancelStreamRef.current();
      setIsStreaming(false);
    }
  };

  return (
    <div className="tab-layout">
      <div className="panel-main">
        <div className="panel-header">
          <h2>Q&A Explainer</h2>
          <div className="header-controls">
            <span className="control-label">Domain Scope:</span>
            <select 
              value={domain} 
              onChange={(e) => setDomain(e.target.value)} 
              className="select-input"
              disabled={isStreaming}
            >
              <option value="max">Max / MSP (General)</option>
              <option value="m4l">Max for Live (LOM API)</option>
            </select>
          </div>
        </div>

        <div className="chat-messages-container">
          {messages.map((msg, idx) => (
            <div key={idx} className={`chat-message ${msg.role === 'user' ? 'msg-user' : 'msg-assistant'}`}>
              <div className="msg-avatar">
                {msg.role === 'user' ? 'U' : 'AI'}
              </div>
              <div className="msg-body">
                {msg.content ? parseMarkdown(msg.content) : <span className="cursor-blink">▋</span>}
              </div>
            </div>
          ))}
          {error && (
            <div className="message-error-banner">
              <strong>Error:</strong> {error}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSubmit} className="chat-input-form">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about object inlets, routing message flow, or LOM structures..."
            className="chat-textarea"
            disabled={isStreaming}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
          />
          <div className="form-actions">
            {isStreaming ? (
              <button key="stop-btn" type="button" onClick={handleStop} className="btn btn-secondary btn-stop">
                Stop Generation
              </button>
            ) : (
              <button key="submit-btn" type="submit" disabled={!input.trim()} className="btn btn-primary">
                Send Query
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
