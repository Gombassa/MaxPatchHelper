import React, { useState } from 'react';
import { api } from '../services/api';

export default function DocExplorer() {
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState(''); // '' (all) | 'max' | 'm4l'
  const [version, setVersion] = useState('8');
  const [limit, setLimit] = useState(3);
  const [results, setResults] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState(null);

  const renderChunkText = (text) => {
    if (!text) return '';
    const urlRegex = /(https:\/\/[^\s\)\(\[\]\{\}\<\>]+)/g;
    const parts = text.split(urlRegex);
    return parts.map((part, index) => {
      if (part.startsWith('https://')) {
        // Strip trailing common punctuation (e.g. .,;:) if matched by mistake
        let cleanUrl = part;
        let trailingPunctuation = '';
        const match = part.match(/([.,;:?]+)$/);
        if (match) {
          trailingPunctuation = match[1];
          cleanUrl = part.slice(0, -trailingPunctuation.length);
        }
        return (
          <React.Fragment key={index}>
            <a
              href={cleanUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--accent-primary)', textDecoration: 'underline' }}
            >
              {cleanUrl}
            </a>
            {trailingPunctuation}
          </React.Fragment>
        );
      }
      return part;
    });
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim() || isSearching) return;

    setError(null);
    setIsSearching(true);
    setResults(null);

    try {
      // Query parameters mapping
      const searchParams = {
        query: query.trim(),
        version: version,
        results: Number(limit)
      };
      
      if (domain) {
        searchParams.domain = domain;
      }

      const data = await api.retrieveDocs(searchParams);
      
      // Parse ChromaDB response structure
      // ChromaDB returns: { ids: [[]], documents: [[]], metadatas: [[]], distances: [[]] }
      if (data && data.documents && data.documents[0]) {
        const documents = data.documents[0];
        const metadatas = data.metadatas[0];
        const ids = data.ids[0];
        const distances = data.distances ? data.distances[0] : [];
        
        const formattedResults = documents.map((doc, idx) => ({
          id: ids[idx],
          content: doc,
          metadata: metadatas[idx] || {},
          distance: distances[idx] !== undefined ? distances[idx].toFixed(4) : 'N/A'
        }));
        
        setResults(formattedResults);
      } else {
        setResults([]);
      }
    } catch (err) {
      console.error(err);
      setError(err.message || 'Failed to search documents.');
    } finally {
      setIsSearching(false);
    }
  };

  const handleCopyChunk = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      alert('Chunk copied to clipboard!');
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="tab-layout split-layout">
      {/* Search Filter Panel */}
      <div className="panel-side">
        <div className="panel-header">
          <h2>Search Filters</h2>
        </div>

        <form onSubmit={handleSearch} className="search-form">
          <div className="form-group">
            <label className="control-label">Search Query:</label>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. cycle~ frequency message, live.path LOM path..."
              className="text-input"
              disabled={isSearching}
            />
          </div>

          <div className="form-group">
            <label className="control-label">Scope Filter:</label>
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="select-input"
              disabled={isSearching}
            >
              <option value="">All Documentation</option>
              <option value="max">Max / MSP (General)</option>
              <option value="m4l">Max for Live (LOM API)</option>
            </select>
          </div>

          <div className="form-group">
            <label className="control-label">Max Version:</label>
            <select
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              className="select-input"
              disabled={isSearching}
            >
              <option value="8">Max 8</option>
              <option value="9">Max 9</option>
            </select>
          </div>

          <div className="form-group">
            <label className="control-label">Result Limit:</label>
            <select
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              className="select-input"
              disabled={isSearching}
            >
              <option value="3">3 Results</option>
              <option value="5">5 Results</option>
              <option value="10">10 Results</option>
            </select>
          </div>

          <div className="form-actions">
            <button type="submit" disabled={!query.trim() || isSearching} className="btn btn-primary btn-block">
              {isSearching ? 'Searching...' : 'Search Vector DB'}
            </button>
          </div>
        </form>
      </div>

      {/* Main Results Panel */}
      <div className="panel-main flex-column">
        <div className="panel-header">
          <h2>Retrieved Document Chunks</h2>
        </div>

        <div className="explorer-results-container">
          {isSearching && (
            <div className="results-spinner-container">
              <div className="spinner"></div>
              <p>Performing semantic search on ChromaDB...</p>
            </div>
          )}

          {error && (
            <div className="message-error-banner">
              <strong>Error:</strong> {error}
            </div>
          )}

          {!isSearching && results === null && (
            <div className="explorer-empty-state">
              <span className="empty-state-icon">🔍</span>
              <h3>Search Max Reference Docs</h3>
              <p>Submit a query on the left to pull exact documentation chunks from the vectorized database.</p>
            </div>
          )}

          {!isSearching && results !== null && results.length === 0 && (
            <div className="explorer-empty-state">
              <h3>No Matches Found</h3>
              <p>Try shortening your terms or modifying the filter settings.</p>
            </div>
          )}

          {!isSearching && results && results.length > 0 && (
            <div className="results-list">
              {results.map((item, idx) => {
                const objectName = item.metadata.object_name || item.metadata.title || 'General Ref';
                const category = item.metadata.category || 'Reference';
                const fileType = item.metadata.file_type || 'refpage';

                return (
                  <div key={idx} className="result-card">
                    <div className="card-header flex-between">
                      <div className="card-title-group">
                        <span className="badge-category">{category}</span>
                        <h4>{objectName}</h4>
                      </div>
                      <span className="text-distance">Distance Score: {item.distance}</span>
                    </div>
                    <div className="card-body">
                      <pre className="result-content-preview">
                        <code>{renderChunkText(item.content)}</code>
                      </pre>
                    </div>
                    <div className="card-footer">
                      <button 
                        className="btn btn-secondary btn-xs" 
                        onClick={() => handleCopyChunk(item.content)}
                      >
                        Copy Chunk Text
                      </button>
                      {item.metadata.source_url && (
                        <a 
                          href={item.metadata.source_url} 
                          target="_blank" 
                          rel="noopener noreferrer" 
                          className="link-source"
                        >
                          Cycling '74 Ref Link
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
