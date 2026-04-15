import React from 'react';
import type { AssistantMessage as MessageType } from '../../hooks/useAssistantChat';

interface AssistantMessageProps {
  message: MessageType;
  onActionClick?: (action: any) => void;
}

function renderContent(text: string): React.ReactNode[] {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];

  lines.forEach((line, i) => {
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        elements.push(
          <pre key={`code-${i}`} className="text-body-xs font-mono text-amber-300/80 bg-duck-bg/80 rounded px-2.5 py-2 my-1.5 overflow-x-auto whitespace-pre-wrap border border-duck-border/20">
            {codeLines.join('\n')}
          </pre>
        );
        codeLines = [];
      }
      inCodeBlock = !inCodeBlock;
    } else if (inCodeBlock) {
      codeLines.push(line);
    } else if (line.match(/^[-•]\s/)) {
      elements.push(
        <div key={i} className="flex items-start gap-2 my-0.5 ml-2">
          <span className="text-duck-accent text-chrome mt-1.5 shrink-0">▸</span>
          <span className="text-slate-200">{line.replace(/^[-•]\s/, '')}</span>
        </div>
      );
    } else if (line.match(/^\d+\.\s/)) {
      elements.push(
        <div key={i} className="flex items-start gap-2 my-0.5 ml-2">
          <span className="text-slate-400 font-mono text-body-xs w-4 shrink-0">{line.match(/^\d+/)?.[0]}.</span>
          <span className="text-slate-200">{line.replace(/^\d+\.\s/, '')}</span>
        </div>
      );
    } else if (line.trim() === '') {
      elements.push(<div key={i} className="h-1.5" />);
    } else {
      const parts = line.split(/(\*\*[^*]+\*\*)/g);
      elements.push(
        <p key={i} className="text-slate-200">
          {parts.map((part, j) =>
            part.startsWith('**') && part.endsWith('**')
              ? <span key={j} className="text-white font-bold">{part.slice(2, -2)}</span>
              : part
          )}
        </p>
      );
    }
  });

  return elements;
}

const AssistantMessageEntry: React.FC<AssistantMessageProps> = ({ message, onActionClick }) => {
  const isUser = message.role === 'user';
  const time = new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  if (isUser) {
    return (
      <div className="flex items-start gap-2 py-1.5 group">
        <span className="text-body-xs font-mono text-slate-400 shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" style={{ fontVariantNumeric: 'tabular-nums' }}>{time}</span>
        <span className="text-duck-accent font-mono text-body-xs shrink-0 mt-0.5">❯</span>
        <span className="text-[13px] font-mono text-white">{message.content}</span>
      </div>
    );
  }

  return (
    <div className="py-1.5 group">
      <div className="pl-5 text-[12px] leading-relaxed">
        {renderContent(message.content)}
      </div>

      {message.actions && message.actions.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2 pl-5">
          {message.actions.map((action, i) => (
            <button
              key={i}
              onClick={() => onActionClick?.(action)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-body-xs font-mono bg-duck-accent/10 text-duck-accent border border-duck-accent/25 hover:bg-duck-accent/20 hover:border-duck-accent/40 transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
            >
              <span className="text-body-xs">→</span>
              {action.type === 'navigate' ? `go ${action.page}` :
               action.type === 'download_report' ? 'download report' :
               action.type === 'start_investigation' ? `run ${action.capability?.replace(/_/g, '-')}` : 'execute'}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default AssistantMessageEntry;
