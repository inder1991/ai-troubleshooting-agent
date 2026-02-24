import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import { motion } from 'framer-motion';
import { messageVariants } from '../../styles/chat-animations';
import { formatTime } from '../../utils/format';
import type { ChatMessage } from '../../types';
import TerminalCodeBlock from './TerminalCodeBlock';

const agentSignatures: Record<string, { label: string; color: string; icon: string }> = {
  log_agent:     { label: 'LOG AGENT',      color: 'red',     icon: 'search' },
  metrics_agent: { label: 'METRICS AGENT',  color: 'cyan',    icon: 'bar_chart' },
  k8s_agent:     { label: 'K8S AGENT',      color: 'orange',  icon: 'dns' },
  tracing_agent: { label: 'TRACING AGENT',  color: 'violet',  icon: 'route' },
  code_agent:    { label: 'CODE AGENT',     color: 'blue',    icon: 'code' },
  change_agent:  { label: 'CHANGE AGENT',   color: 'emerald', icon: 'difference' },
  critic:        { label: 'CRITIC',         color: 'amber',   icon: 'gavel' },
  fix_generator: { label: 'FIX GENERATOR',  color: 'pink',    icon: 'build' },
  supervisor:    { label: 'SRE FOREMAN',    color: 'cyan',    icon: 'psychology' },
};

const colorMap: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  red:     { bg: 'bg-red-500/10',     border: 'border-l-red-400',     text: 'text-red-400',     badge: 'bg-red-500/20' },
  cyan:    { bg: 'bg-cyan-500/10',    border: 'border-l-cyan-400',    text: 'text-cyan-400',    badge: 'bg-cyan-500/20' },
  orange:  { bg: 'bg-orange-500/10',  border: 'border-l-orange-400',  text: 'text-orange-400',  badge: 'bg-orange-500/20' },
  violet:  { bg: 'bg-violet-500/10',  border: 'border-l-violet-400',  text: 'text-violet-400',  badge: 'bg-violet-500/20' },
  blue:    { bg: 'bg-blue-500/10',    border: 'border-l-blue-400',    text: 'text-blue-400',    badge: 'bg-blue-500/20' },
  emerald: { bg: 'bg-emerald-500/10', border: 'border-l-emerald-400', text: 'text-emerald-400', badge: 'bg-emerald-500/20' },
  amber:   { bg: 'bg-amber-500/10',   border: 'border-l-amber-400',   text: 'text-amber-400',   badge: 'bg-amber-500/20' },
  pink:    { bg: 'bg-pink-500/10',    border: 'border-l-pink-400',    text: 'text-pink-400',    badge: 'bg-pink-500/20' },
};

function detectAgent(message: ChatMessage): { label: string; color: string; icon: string } {
  // Check metadata first
  const agentKey = message.metadata?.type;
  if (agentKey && agentSignatures[agentKey]) {
    return agentSignatures[agentKey];
  }

  // Content-based fallback detection
  const content = message.content.toLowerCase();
  if (content.includes('log') && content.includes('analy')) return agentSignatures.log_agent;
  if (content.includes('metric') || content.includes('prometheus')) return agentSignatures.metrics_agent;
  if (content.includes('kubernetes') || content.includes('k8s') || content.includes('pod')) return agentSignatures.k8s_agent;
  if (content.includes('code') && (content.includes('file') || content.includes('function'))) return agentSignatures.code_agent;

  return agentSignatures.supervisor;
}

// Custom components for react-markdown
const markdownComponents = {
  code: ({ children, className, ...props }: { children?: React.ReactNode; className?: string; node?: unknown }) => {
    const { node: _node, ...rest } = props as Record<string, unknown>;
    const isInline = !className;
    const content = String(children).replace(/\n$/, '');
    return (
      <TerminalCodeBlock className={className} inline={isInline} {...rest}>
        {content}
      </TerminalCodeBlock>
    );
  },
};

interface MarkdownBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
  streamingContent?: string;
}

const MarkdownBubbleInner: React.FC<MarkdownBubbleProps> = ({ message, isStreaming, streamingContent }) => {
  const isUser = message.role === 'user';
  const isError = message.metadata?.type === 'error';

  // For streaming, close any dangling code fences
  const displayContent = useMemo(() => {
    if (!isStreaming || !streamingContent) return message.content;
    const openFences = (streamingContent.match(/```/g) || []).length;
    if (openFences % 2 !== 0) {
      return streamingContent + '\n```';
    }
    return streamingContent;
  }, [isStreaming, streamingContent, message.content]);

  // User bubble
  if (isUser) {
    return (
      <motion.div
        variants={messageVariants}
        initial="hidden"
        animate="visible"
        className="flex justify-end mb-3"
      >
        <div className="max-w-[85%] bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-3 py-2">
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[9px] font-bold text-cyan-400/60 tracking-wider">○ OPERATOR</span>
          </div>
          <p className="text-[13px] text-slate-200 font-mono whitespace-pre-wrap">{message.content}</p>
          <div className="text-right mt-1">
            <span className="text-[9px] text-slate-600">{formatTime(message.timestamp)}</span>
          </div>
        </div>
      </motion.div>
    );
  }

  // Assistant bubble
  const agent = detectAgent(message);
  const colors = colorMap[agent.color] || colorMap.cyan;

  return (
    <motion.div
      variants={messageVariants}
      initial="hidden"
      animate="visible"
      className="mb-3"
    >
      <div className={`max-w-[95%] ${colors.bg} border-l-[3px] ${colors.border} rounded-r-lg px-3 py-2 ${isError ? 'border border-red-500/20' : ''}`}>
        {/* Agent badge */}
        <div className="flex items-center gap-1.5 mb-1.5">
          <span
            className={`material-symbols-outlined ${colors.text}`}
            style={{ fontFamily: 'Material Symbols Outlined', fontSize: '14px' }}
          >
            {agent.icon}
          </span>
          <span className={`text-[9px] font-bold ${colors.text} tracking-wider`}>
            ● {agent.label}
          </span>
        </div>

        {/* Message content — markdown for assistant, raw for errors */}
        {isError ? (
          <p className="text-[13px] text-red-300 font-mono">{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none text-[13px] text-slate-200 leading-relaxed">
            <ReactMarkdown
              rehypePlugins={[rehypeHighlight, rehypeRaw]}
              components={markdownComponents}
            >
              {displayContent}
            </ReactMarkdown>
            {isStreaming && <span className="streaming-cursor" />}
          </div>
        )}

        {/* Timestamp */}
        <div className="text-right mt-1">
          <span className="text-[9px] text-slate-600">{formatTime(message.timestamp)}</span>
        </div>
      </div>
    </motion.div>
  );
};

// Memoize non-streaming messages for performance
const MarkdownBubble = React.memo(MarkdownBubbleInner, (prev, next) => {
  // Never memoize streaming messages — they re-render on every chunk
  if (next.isStreaming) return false;
  return prev.message === next.message && prev.isStreaming === next.isStreaming;
});

export default MarkdownBubble;
