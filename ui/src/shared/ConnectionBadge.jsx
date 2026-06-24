import React from 'react';

/**
 * Reusable badge to indicate server, SSE, or WebSocket connection status.
 * Accepts: status ('connected' | 'connecting' | 'disconnected') and optional label.
 */
export default function ConnectionBadge({ status, label }) {
  const getBadgeClass = () => {
    switch (status) {
      case 'connected':
        return 'badge-connected';
      case 'connecting':
        return 'badge-connecting';
      case 'disconnected':
      default:
        return 'badge-disconnected';
    }
  };

  const getStatusText = () => {
    if (label) return label;
    switch (status) {
      case 'connected':
        return 'Connected';
      case 'connecting':
        return 'Connecting...';
      case 'disconnected':
      default:
        return 'Disconnected';
    }
  };

  return (
    <div className={`status-badge ${getBadgeClass()}`}>
      <span className="badge-dot"></span>
      <span className="badge-text">{getStatusText()}</span>
    </div>
  );
}
