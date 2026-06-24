import React, { useState } from 'react';

/**
 * Reusable CodeBlock component supporting:
 * - Syntax container
 * - Copy to clipboard action
 * - Save/download to file action (specifically for MaxPat json)
 */
export default function CodeBlock({ code, language = 'json', fileName = 'patch.maxpat' }) {
  const [copied, setCopied] = useState(false);

  const formattedCode = typeof code === 'object' 
    ? JSON.stringify(code, null, 2) 
    : code;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(formattedCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  const handleDownload = () => {
    try {
      const blob = new Blob([formattedCode], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download file: ', err);
    }
  };

  return (
    <div className="code-block-container">
      <div className="code-block-header">
        <span className="code-block-lang">{language.toUpperCase()}</span>
        <div className="code-block-actions">
          <button className="btn-icon" onClick={handleCopy} title="Copy to clipboard">
            {copied ? 'Copied!' : 'Copy'}
          </button>
          {language === 'json' && (
            <button className="btn-icon btn-download" onClick={handleDownload} title="Download Max Pat file">
              Download .maxpat
            </button>
          )}
        </div>
      </div>
      <pre className="code-block-pre">
        <code className="code-block-content">{formattedCode}</code>
      </pre>
    </div>
  );
}
