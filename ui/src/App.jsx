import React, { useState, useEffect } from 'react';
import './App.css';
import { api } from './services/api';

// Import Tab Components
import Explainer from './components/Explainer';
import DocExplorer from './components/DocExplorer';
import ConnectionBadge from './shared/ConnectionBadge';

function App() {
  const [activeTab, setActiveTab] = useState('explain'); // 'explain' | 'explore'
  const [backendStatus, setBackendStatus] = useState('connecting'); // 'connected' | 'connecting' | 'disconnected'
  const [models, setModels] = useState(null);

  // Verify FastAPI Backend Health on startup
  useEffect(() => {
    let active = true;

    async function checkHealth() {
      try {
        const data = await api.getHealth();
        if (active) {
          setBackendStatus('connected');
          setModels(data.models);
        }
      } catch (err) {
        console.error("Backend health check failed:", err);
        if (active) {
          setBackendStatus('disconnected');
        }
      }
    }

    checkHealth();

    // Check health every 15 seconds
    const interval = setInterval(checkHealth, 15000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="app-shell">
      {/* Shell Header */}
      <header className="app-header">
        <div className="logo-section">
          <span className="logo-icon">🚀</span>
          <h1>Max Patch Helper</h1>
          <span className="logo-badge">v1.0.0</span>
        </div>

        {/* Global Connection Badge */}
        <div className="health-section">
          <span className="health-label">FastAPI Server:</span>
          <ConnectionBadge 
            status={backendStatus} 
            label={backendStatus === 'connected' ? 'Server Online' : backendStatus === 'connecting' ? 'Connecting...' : 'Server Offline'} 
          />
          {backendStatus === 'connected' && models && (
            <span className="model-info">
              [{models.explain}]
            </span>
          )}
        </div>
      </header>

      {/* Main Tabbed Navigation Container */}
      <nav className="tab-navigation">
        <button 
          className={`tab-btn ${activeTab === 'explain' ? 'active' : ''}`}
          onClick={() => setActiveTab('explain')}
        >
          💬 Q&A Explainer
        </button>
        <button
          className={`tab-btn ${activeTab === 'explore' ? 'active' : ''}`}
          onClick={() => setActiveTab('explore')}
        >
          🔍 Document Explorer
        </button>
      </nav>

      {/* Keep-Alive Pane Layout Render Tree */}
      <main className="app-content">
        <div className={`tab-pane ${activeTab === 'explain' ? 'active' : 'hidden'}`}>
          <Explainer />
        </div>
        <div className={`tab-pane ${activeTab === 'explore' ? 'active' : 'hidden'}`}>
          <DocExplorer />
        </div>
      </main>
    </div>
  );
}

export default App;
