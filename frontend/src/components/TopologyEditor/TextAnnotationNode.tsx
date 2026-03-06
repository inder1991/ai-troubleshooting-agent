import React, { memo } from 'react';
import { Handle, Position, type NodeProps, NodeResizeControl } from 'reactflow';

interface TextAnnotationData {
  label?: string;
  text: string;
  fontSize?: number;
  color?: string;
  backgroundColor?: string;
  borderStyle?: 'none' | 'dashed' | 'solid';
}

const TextAnnotationNode: React.FC<NodeProps<TextAnnotationData>> = ({ data, selected }) => {
  const fontSize = data.fontSize || 12;
  const color = data.color || '#e2e8f0';
  const bg = data.backgroundColor || 'transparent';
  const borderStyle = data.borderStyle || 'none';

  return (
    <div className="relative group">
      <NodeResizeControl minWidth={40} minHeight={20}
        style={{ background: '#07b6d5', width: '8px', height: '8px', borderRadius: '2px' }}
      />

      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#64748b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#64748b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#64748b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#64748b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <div
        className="w-full h-full font-mono whitespace-pre-wrap break-words p-2"
        style={{
          fontSize: `${fontSize}px`,
          color,
          backgroundColor: bg,
          border: borderStyle === 'none' ? (selected ? '1px dashed #07b6d540' : 'none') : `1px ${borderStyle} ${selected ? '#07b6d5' : '#64748b40'}`,
          borderRadius: '4px',
          lineHeight: 1.4,
        }}
      >
        {data.text || data.label || ''}
      </div>
    </div>
  );
};

export default memo(TextAnnotationNode);
