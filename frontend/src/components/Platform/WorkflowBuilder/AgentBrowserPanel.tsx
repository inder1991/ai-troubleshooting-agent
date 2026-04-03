import React from 'react';

interface Props {
  onInsertAgent: (agentId: string) => void;
}

const AgentBrowserPanel: React.FC<Props> = () => {
  return (
    <div className="flex items-center justify-center h-full text-xs font-sans" style={{ color: '#3d4a50', background: '#0a1214' }}>
      Loading agents...
    </div>
  );
};

export default AgentBrowserPanel;
