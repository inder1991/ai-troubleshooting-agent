import React, { useState, useRef, useCallback, useEffect } from 'react';
import SlashCommandMenu, { SLASH_COMMANDS } from './SlashCommandMenu';

interface ChatInputAreaProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
  onEscDrawer?: () => void;
}

const ChatInputArea: React.FC<ChatInputAreaProps> = ({
  onSend,
  disabled = false,
  placeholder = 'Ask the crew anything... (type / for commands)',
  onEscDrawer,
}) => {
  const [input, setInput] = useState('');
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const [slashSelectedIndex, setSlashSelectedIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [input, adjustHeight]);

  // Detect slash command typing
  useEffect(() => {
    if (input.startsWith('/')) {
      setShowSlashMenu(true);
      setSlashFilter(input);
      setSlashSelectedIndex(0);
    } else {
      setShowSlashMenu(false);
    }
  }, [input]);

  const filteredCommands = SLASH_COMMANDS.filter(
    c => c.cmd.toLowerCase().includes(slashFilter.toLowerCase()) ||
         c.label.toLowerCase().includes(slashFilter.toLowerCase())
  );

  const handleSlashSelect = useCallback((cmd: string) => {
    setInput(cmd + ' ');
    setShowSlashMenu(false);
    textareaRef.current?.focus();
  }, []);

  const handleSend = useCallback(() => {
    if (!input.trim() || disabled) return;
    onSend(input.trim());
    setInput('');
    setShowSlashMenu(false);
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [input, disabled, onSend]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Slash menu navigation
    if (showSlashMenu) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSlashSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSlashSelectedIndex(i => Math.max(i - 1, 0));
        return;
      }
      if ((e.key === 'Enter' || e.key === 'Tab') && filteredCommands.length > 0) {
        e.preventDefault();
        handleSlashSelect(filteredCommands[slashSelectedIndex].cmd);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowSlashMenu(false);
        return;
      }
    }

    // Enter to send (without shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
      return;
    }

    // Two-stage Escape: close slash menu first, then close drawer
    if (e.key === 'Escape') {
      e.preventDefault();
      onEscDrawer?.();
    }
  }, [showSlashMenu, filteredCommands, slashSelectedIndex, handleSlashSelect, handleSend, onEscDrawer]);

  return (
    <div className="relative shrink-0 p-3 border-t border-slate-800/50">
      {/* Slash command menu */}
      {showSlashMenu && (
        <SlashCommandMenu
          filter={slashFilter}
          selectedIndex={slashSelectedIndex}
          onSelect={handleSlashSelect}
          onClose={() => setShowSlashMenu(false)}
        />
      )}

      {/* Input area */}
      <div className="relative flex items-end gap-2 bg-slate-800/50 border border-slate-700/50 rounded-lg focus-within:border-cyan-500/50 transition-colors">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="flex-1 bg-transparent text-sm text-slate-200 font-mono px-3 py-2.5 resize-none outline-none placeholder:text-slate-600 disabled:opacity-50"
          style={{ maxHeight: '120px' }}
        />
        <button
          onClick={handleSend}
          disabled={disabled || !input.trim()}
          className="shrink-0 p-2 mr-1 mb-0.5 rounded-md bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500 text-white transition-colors"
          title="Send message"
        >
          <span
            className="material-symbols-outlined"
            style={{ fontFamily: 'Material Symbols Outlined', fontSize: '16px' }}
          >
            send
          </span>
        </button>
      </div>
    </div>
  );
};

export default ChatInputArea;
