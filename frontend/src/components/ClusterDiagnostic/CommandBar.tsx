import React, { useState, useCallback } from 'react';
import { useChatUI } from '../../contexts/ChatContext';

const CommandBar: React.FC = () => {
  const [input, setInput] = useState('');
  const { sendMessage, openDrawer } = useChatUI();

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed) return;
    sendMessage(trimmed);
    openDrawer();
    setInput('');
  }, [input, sendMessage, openDrawer]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  return (
    <footer className="h-12 bg-[#152a2f] border-t border-[#1f3b42] sticky bottom-0 z-50 flex items-center px-4 shrink-0">
      <div className="flex items-center gap-3 w-full max-w-4xl mx-auto">
        <span className="text-[#13b6ec] font-mono text-sm font-bold">$</span>
        <input
          className="bg-transparent border-none text-sm font-mono text-white w-full placeholder-slate-600 focus:outline-none focus:ring-0"
          placeholder="Type tactical command (e.g., /cordon --node=3) or press 'K' for quick search..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="flex gap-2 shrink-0">
          <kbd className="px-2 py-0.5 bg-[#0f2023] border border-[#1f3b42] rounded text-[10px] font-mono text-slate-400 uppercase">Shift</kbd>
          <kbd className="px-2 py-0.5 bg-[#0f2023] border border-[#1f3b42] rounded text-[10px] font-mono text-slate-400 uppercase">Enter</kbd>
        </div>
      </div>
    </footer>
  );
};

export default CommandBar;
