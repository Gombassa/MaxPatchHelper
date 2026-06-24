import React, { useState, useEffect, useRef } from 'react';
import { connectGuidedWebSocket } from '../services/api';
import ConnectionBadge from '../shared/ConnectionBadge';
import CodeBlock from '../shared/CodeBlock';
import { parseMarkdown } from './Explainer';

export default function GuidedBuilder() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState('disconnected');
  const [spec, setSpec] = useState('No specification defined yet. Describe your patch ideas to build one.');
  const [idioms, setIdioms] = useState('');
  const [generatedPatch, setGeneratedPatch] = useState(null);
  
  // Track ongoing LLM streaming tokens
  const [streamingToken, setStreamingToken] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [genLogs, setGenLogs] = useState([]);

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingToken, genLogs]);

  const [sessionStarted, setSessionStarted] = useState(false);

  // Connect only when sessionStarted is true
  useEffect(() => {
    if (!sessionStarted) return;

    const ws = connectGuidedWebSocket({
      onStatusChange: (newStatus) => {
        setStatus(newStatus);
      },
      onMessage: (data) => {
        if (data.type === 'status') {
          // If it's a general server message, append to chat history as system role
          setMessages(prev => [...prev, { role: 'system', content: data.content }]);
        } else if (data.type === 'idioms') {
          setIdioms(data.content);
        } else if (data.type === 'token') {
          // Accumulate streaming assistant message
          setStreamingToken(prev => prev + data.content);
        } else if (data.type === 'spec') {
          setSpec(data.content);
        } else if (data.type === 'error') {
          const errText = Array.isArray(data.content) ? data.content.join(', ') : data.content;
          setMessages(prev => [...prev, { role: 'error', content: `[Error]: ${errText}` }]);
          setIsGenerating(false);
        } else if (data.type === 'patch') {
          setGeneratedPatch(data.content);
          setIsGenerating(false);
          setMessages(prev => [...prev, { 
            role: 'system', 
            content: 'Success! A valid Max patch has been compiled and is ready for download.' 
          }]);
        }
      }
    });

    wsRef.current = ws;

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [sessionStarted]);

  // Flush streaming token to message history when LLM finishes a turn
  useEffect(() => {
    // If the websocket goes quiet or we detect the assistant turn is complete:
    // Actually, in the WS server run_websocket_llm_turn completes and returns full_response.
    // The server doesn't send an explicit "done" tag, but it sends a 'spec' or 'status' message right after.
    // We can commit the streaming token to messages whenever spec changes or when we send a new user message.
  }, [spec]);

  // We can write a cleaner way to commit the streaming assistant message.
  // Whenever the streaming token gets modified, we can check if it's been a while,
  // or simply when the user submits their next message we flush it, or when the server sends a spec update.
  // Let's flush streamingToken whenever a new event like 'spec' or 'status' or 'patch' comes in.
  useEffect(() => {
    if (streamingToken) {
      // Find if we have an active assistant bubble to update, or append a temporary one
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant' && last.isStreaming) {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', content: streamingToken, isStreaming: true };
          return updated;
        } else {
          return [...prev, { role: 'assistant', content: streamingToken, isStreaming: true }];
        }
      });
    }
  }, [streamingToken]);

  // When spec updates, we finalize the assistant streaming message (remove isStreaming flag)
  useEffect(() => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last && last.role === 'assistant' && last.isStreaming) {
        const updated = [...prev];
        updated[updated.length - 1] = { role: 'assistant', content: last.content, isStreaming: false };
        return updated;
      }
      return prev;
    });
    setStreamingToken('');
  }, [spec]);

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!input.trim() || status !== 'connected') return;

    const text = input.trim();
    setInput('');

    // Clear previous patch if we are refining
    setGeneratedPatch(null);

    // Commit any stray streaming tokens
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last && last.role === 'assistant' && last.isStreaming) {
        const updated = [...prev];
        updated[updated.length - 1] = { role: 'assistant', content: last.content, isStreaming: false };
        return [...updated, { role: 'user', content: text }];
      }
      return [...prev, { role: 'user', content: text }];
    });
    setStreamingToken('');

    try {
      wsRef.current.sendChat(text);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'error', content: `Send failed: ${err.message}` }]);
    }
  };

  const handleGenerate = () => {
    if (status !== 'connected') return;
    setIsGenerating(true);
    setGeneratedPatch(null);
    setMessages(prev => [...prev, { role: 'system', content: '[System] Compiling spec and starting validation loop...' }]);
    try {
      wsRef.current.sendGenerate();
    } catch (err) {
      setMessages(prev => [...prev, { role: 'error', content: `Trigger failed: ${err.message}` }]);
      setIsGenerating(false);
    }
  };

  const handleExit = () => {
    if (status !== 'connected') return;
    if (window.confirm("End session? This runs the learning stage to compile idioms and closes the socket.")) {
      try {
        wsRef.current.sendExit();
      } catch (err) {
        console.error(err);
      }
    }
  };

  return (
    <div className="tab-layout split-layout">
      {/* Left Column: Chat Conversation */}
      <div className="panel-main flex-column">
        <div className="panel-header">
          <div className="title-area">
            <h2>Guided Spec Builder</h2>
            {sessionStarted && <ConnectionBadge status={status} />}
          </div>
          <div className="header-controls">
            {sessionStarted && status === 'disconnected' && (
              <button 
                onClick={() => setSessionStarted(false)} 
                className="btn btn-secondary btn-sm"
              >
                Reset & Start New Session
              </button>
            )}
            {sessionStarted && status === 'connected' && (
              <>
                <button 
                  onClick={handleGenerate} 
                  className="btn btn-success btn-sm"
                  disabled={isGenerating}
                >
                  Compile & Generate Patch
                </button>
                <button 
                  onClick={handleExit} 
                  className="btn btn-danger btn-sm"
                >
                  End Session (Save Idioms)
                </button>
              </>
            )}
          </div>
        </div>

        {!sessionStarted ? (
          <div className="chat-empty-state">
            <span className="empty-state-icon">🤖</span>
            <h3>Guided Specification Builder</h3>
            <p>
              This stateful mode helps you design Max patches interactively. 
              The assistant will query your design needs, compile a live specification list, and automatically summarize lessons learned into your design idioms.
            </p>
            <button 
              onClick={() => {
                setMessages([]);
                setGeneratedPatch(null);
                setSpec('No specification defined yet. Describe your patch ideas to build one.');
                setSessionStarted(true);
              }} 
              className="btn btn-primary"
              style={{ marginTop: 'var(--spacing-md)' }}
            >
              Start Guided Session
            </button>
          </div>
        ) : (
          <>
            <div className="chat-messages-container">
              {messages.length === 0 && (
                <div className="chat-empty-state">
                  <span className="empty-state-icon">⚡</span>
                  <h3>Session Initialized</h3>
                  <p>WebSocket connection established. Waiting for past design history...</p>
                </div>
              )}
              
              {messages.map((msg, idx) => {
                let className = "chat-message ";
                let avatar = "AI";
                if (msg.role === 'user') {
                  className += "msg-user";
                  avatar = "U";
                } else if (msg.role === 'system') {
                  className += "msg-system";
                  avatar = "⚙️";
                } else if (msg.role === 'error') {
                  className += "msg-error";
                  avatar = "❌";
                } else {
                  className += "msg-assistant";
                }

                return (
                  <div key={idx} className={className}>
                    <div className="msg-avatar">{avatar}</div>
                    <div className="msg-body">
                      {parseMarkdown(msg.content)}
                    </div>
                  </div>
                );
              })}
              
              {/* Output generated patch code directly in the chat once complete */}
              {generatedPatch && (
                <div className="chat-message msg-system">
                  <div className="msg-avatar">💾</div>
                  <div className="msg-body">
                    <p><strong>Generated Patch File:</strong></p>
                    <CodeBlock 
                      code={generatedPatch} 
                      language="json" 
                      fileName="guided_patch.maxpat"
                    />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <form onSubmit={handleSendMessage} className="chat-input-form">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type your design requirements or answers to the assistant's questions..."
                className="chat-textarea"
                disabled={status !== 'connected' || isGenerating}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage(e);
                  }
                }}
              />
              <div className="form-actions">
                <button 
                  type="submit" 
                  disabled={!input.trim() || status !== 'connected' || isGenerating} 
                  className="btn btn-primary"
                >
                  Send Requirement
                </button>
              </div>
            </form>
          </>
        )}
      </div>

      {/* Right Column: Spec & Idioms Sidebars */}
      <div className="panel-side layout-sidebar">
        {/* Specification Panel */}
        <div className="sidebar-card spec-card">
          <div className="card-header">
            <h3>Current Specification</h3>
          </div>
          <div className="card-body markdown-container">
            {parseMarkdown(spec)}
          </div>
        </div>

        {/* Loaded Idioms Panel */}
        <div className="sidebar-card idioms-card">
          <div className="card-header">
            <h3>Design History Summary</h3>
          </div>
          <div className="card-body markdown-container">
            {idioms ? (
              parseMarkdown(idioms)
            ) : (
              <div className="idioms-empty">
                No past personal idioms summary loaded for this session. Complete a session to save design lessons.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
