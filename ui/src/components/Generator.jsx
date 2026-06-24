import React, { useState, useRef, useEffect } from 'react';
import { api } from '../services/api';
import CodeBlock from '../shared/CodeBlock';

export default function Generator() {
  const [prompt, setPrompt] = useState('');
  const [domain, setDomain] = useState('max'); // 'max' | 'm4l'
  const [logs, setLogs] = useState([]);
  const [generatedPatch, setGeneratedPatch] = useState(null);
  const [streamingToken, setStreamingToken] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessages, setErrorMessages] = useState([]);

  const logsEndRef = useRef(null);
  const cancelStreamRef = useRef(null);

  const scrollToBottom = () => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [logs, streamingToken]);

  useEffect(() => {
    return () => {
      if (cancelStreamRef.current) cancelStreamRef.current();
    };
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!prompt.trim() || isGenerating) return;

    // Reset states
    setLogs([]);
    setGeneratedPatch(null);
    setStreamingToken('');
    setErrorMessages([]);
    setIsGenerating(true);

    addLog('System', `Initiating patch generation for: "${prompt.trim()}"`);
    addLog('System', `Domain scope: ${domain === 'm4l' ? 'Max for Live (M4L)' : 'Max / MSP (General)'}`);

    let currentLogs = [];
    let currentToken = '';

    const cancel = api.streamGenerate(
      { query: prompt.trim(), domain: domain, version: '8' },
      {
        onMessage: (data) => {
          // Format message based on payload type
          if (data.type === 'status') {
            addLog('Server', data.content);
            setStreamingToken(''); // Clear token display when a new status block arrives
          } else if (data.type === 'token') {
            currentToken += data.content;
            setStreamingToken(currentToken);
          } else if (data.type === 'error') {
            const errs = Array.isArray(data.content) ? data.content : [data.content];
            setErrorMessages(errs);
            addLog('Error', `Generation failed. Errors:\n- ${errs.join('\n- ')}`);
            setIsGenerating(false);
          } else if (data.type === 'patch') {
            setGeneratedPatch(data.content);
            addLog('System', 'Patch generation complete! Validated patch received.');
            setIsGenerating(false);
          }
        },
        onError: (err) => {
          console.error("Generator stream error:", err);
          addLog('Error', `Server communication failed: ${err.message || err}`);
          setIsGenerating(false);
        },
        onDone: () => {
          setIsGenerating(false);
        }
      }
    );

    cancelStreamRef.current = cancel;
  };

  const addLog = (source, message) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { timestamp, source, message }]);
  };

  const handleStop = (e) => {
    if (e) e.preventDefault();
    if (cancelStreamRef.current) {
      cancelStreamRef.current();
      addLog('System', 'Generation stream cancelled by user.');
      setIsGenerating(false);
    }
  };

  return (
    <div className="tab-layout split-layout">
      {/* Left Panel: Prompt and Log Terminal */}
      <div className="panel-side">
        <div className="panel-header">
          <h2>Prompt & Logs</h2>
        </div>

        <form onSubmit={handleSubmit} className="generator-form">
          <div className="form-group">
            <label className="control-label">Domain Scope:</label>
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="select-input"
              disabled={isGenerating}
            >
              <option value="max">Max / MSP (General)</option>
              <option value="m4l">Max for Live (M4L)</option>
            </select>
          </div>

          <div className="form-group">
            <label className="control-label">Prompt:</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g., a dual-oscillator FM synthesizer with mod index control and a volume slider..."
              className="chat-textarea"
              disabled={isGenerating}
              rows={4}
            />
          </div>

          <div className="form-actions">
            {isGenerating ? (
              <button key="stop-btn" type="button" onClick={handleStop} className="btn btn-secondary btn-stop">
                Stop Generation
              </button>
            ) : (
              <button key="submit-btn" type="submit" disabled={!prompt.trim()} className="btn btn-primary">
                Generate Patch
              </button>
            )}
          </div>
        </form>

        {/* Log Console Terminal */}
        <div className="log-console-container">
          <div className="console-header">
            <span>Validation Logs Console</span>
          </div>
          <div className="console-body">
            {logs.length === 0 && !isGenerating && (
              <div className="console-placeholder">Terminal logs will appear here during generation...</div>
            )}
            {logs.map((log, idx) => (
              <div key={idx} className={`console-line source-${log.source.toLowerCase()}`}>
                <span className="console-time">[{log.timestamp}]</span>{' '}
                <span className="console-source">[{log.source}]:</span>{' '}
                <span className="console-message">{log.message}</span>
              </div>
            ))}
            {streamingToken && (
              <div className="console-line source-token">
                <span className="console-source">[LLM Stream]:</span>{' '}
                <span className="console-stream-content">{streamingToken}</span>
                <span className="cursor-blink">▋</span>
              </div>
            )}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>

      {/* Right Panel: Output Code Block */}
      <div className="panel-main flex-column">
        <div className="panel-header">
          <h2>Output Patch (.maxpat)</h2>
        </div>

        <div className="generator-output-container">
          {generatedPatch ? (
            <CodeBlock 
              code={generatedPatch} 
              language="json" 
              fileName="generated_patch.maxpat"
            />
          ) : (
            <div className="generator-placeholder-container">
              {isGenerating ? (
                <div className="generator-spinner-container">
                  <div className="spinner"></div>
                  <p>Model is generating and validating patch code...</p>
                  <p className="subtext">This takes up to 1-2 minutes depending on validator retries.</p>
                </div>
              ) : errorMessages.length > 0 ? (
                <div className="generator-error-display">
                  <h3>Validation Loop Failed</h3>
                  <p>The model was unable to generate a valid Max patch after 3 attempts. Errors found:</p>
                  <ul className="error-list">
                    {errorMessages.map((err, idx) => (
                      <li key={idx}>{err}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="generator-empty-state">
                  <span className="empty-state-icon">⚡</span>
                  <h3>No Patch Generated Yet</h3>
                  <p>Enter a description and click "Generate Patch" to begin.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
