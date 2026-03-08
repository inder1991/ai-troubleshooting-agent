import React, { useState, useMemo } from 'react';
import type { IPAMTreeNode } from '../../types';

interface Props {
  tree: IPAMTreeNode[];
  selectedSubnetId: string;
  onSelectSubnet: (subnetId: string) => void;
  onSelectNode?: (nodeId: string, nodeType: string) => void;
  onContextMenu?: (e: React.MouseEvent, subnetId: string, cidr: string) => void;
}

function utilizationColor(pct: number | undefined): string {
  if (pct === undefined) return 'bg-slate-600';
  if (pct >= 80) return 'bg-red-500';
  if (pct >= 50) return 'bg-amber-500';
  return 'bg-emerald-500';
}

function statusDot(pct: number | undefined): string {
  if (pct === undefined) return 'bg-slate-500';
  if (pct >= 90) return 'bg-red-500';
  if (pct >= 70) return 'bg-amber-500';
  return 'bg-emerald-500';
}

function matchesFilter(node: IPAMTreeNode, filter: string): boolean {
  const lower = filter.toLowerCase();
  if (node.label.toLowerCase().includes(lower)) return true;
  if (node.cidr && node.cidr.toLowerCase().includes(lower)) return true;
  if (node.children?.some((c) => matchesFilter(c, filter))) return true;
  return false;
}

function TreeNode({
  node,
  depth,
  selectedSubnetId,
  onSelectSubnet,
  onSelectNode,
  onContextMenu,
  filter,
}: {
  node: IPAMTreeNode;
  depth: number;
  selectedSubnetId: string;
  onSelectSubnet: (id: string) => void;
  onSelectNode?: (id: string, type: string) => void;
  onContextMenu?: (e: React.MouseEvent, subnetId: string, cidr: string) => void;
  filter: string;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  const isSubnet = node.type === 'subnet';
  const isSelected = isSubnet && node.id === selectedSubnetId;
  const showUtilBar = isSubnet || node.type === 'address_block';

  const iconMap: Record<string, string> = {
    region: 'public',
    vpc: 'cloud',
    zone: 'dns',
    subnet: 'hub',
    site: 'domain',
    vrf: 'route',
    address_block: 'grid_view',
  };

  // Count children for non-subnet nodes
  const childCount = !isSubnet && hasChildren ? node.children.length : 0;

  // Filter: if a filter is active and this node doesn't match, hide it
  if (filter && !matchesFilter(node, filter)) return null;

  return (
    <div>
      <button
        onClick={() => {
          if (isSubnet) {
            onSelectSubnet(node.id);
          } else if (node.type === 'address_block') {
            onSelectNode?.(node.id, node.type);
            setExpanded(!expanded);
          } else {
            setExpanded(!expanded);
          }
        }}
        onContextMenu={isSubnet && onContextMenu ? (e) => onContextMenu(e, node.id, node.cidr || '') : undefined}
        className={`w-full flex items-center gap-1.5 px-2 py-1.5 text-sm rounded hover:bg-[#1e3a40] transition-colors ${
          isSelected ? 'bg-[#1e3a40] border-l-2 border-cyan-400' : ''
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {/* Expand/Collapse arrow */}
        {hasChildren && !isSubnet ? (
          <span className="material-symbols-outlined text-xs text-slate-500 w-4 flex-shrink-0">
            {expanded ? 'expand_more' : 'chevron_right'}
          </span>
        ) : (
          <span className="w-4 flex-shrink-0" />
        )}
        {/* Status dot — SolarWinds style */}
        {isSubnet ? (
          <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${statusDot(node.utilization_pct)}`} />
        ) : (
          <span className="material-symbols-outlined text-sm text-slate-400 flex-shrink-0">
            {iconMap[node.type] || 'folder'}
          </span>
        )}
        {/* Label */}
        <span className={`flex-1 text-left truncate ${isSelected ? 'text-cyan-300 font-medium' : 'text-slate-300'}`}>
          {node.label}
        </span>
        {/* Child count badge for non-subnet nodes */}
        {childCount > 0 && !isSubnet && (
          <span className="px-1.5 py-0.5 rounded-full bg-slate-700 text-[10px] text-slate-400 flex-shrink-0">
            {childCount}
          </span>
        )}
        {/* CIDR + utilization for subnet & address_block nodes */}
        {showUtilBar && node.cidr && (
          <span className="font-mono text-[10px] text-slate-500 flex-shrink-0">{node.cidr}</span>
        )}
        {showUtilBar && node.utilization_pct !== undefined && (
          <div className="flex items-center gap-1 ml-1 flex-shrink-0">
            <div className="w-10 h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${utilizationColor(node.utilization_pct)}`}
                style={{ width: `${Math.min(node.utilization_pct, 100)}%` }}
              />
            </div>
            <span className="text-[10px] text-slate-500 w-7 text-right">
              {node.utilization_pct}%
            </span>
          </div>
        )}
      </button>
      {expanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedSubnetId={selectedSubnetId}
              onSelectSubnet={onSelectSubnet}
              onSelectNode={onSelectNode}
              onContextMenu={onContextMenu}
              filter={filter}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function IPAMHierarchyTree({ tree, selectedSubnetId, onSelectSubnet, onSelectNode, onContextMenu }: Props) {
  const [filter, setFilter] = useState('');

  const filteredTree = useMemo(() => {
    if (!filter) return tree;
    return tree.filter((node) => matchesFilter(node, filter));
  }, [tree, filter]);

  if (!tree.length) {
    return (
      <div className="text-center text-slate-500 py-8 text-sm">
        No subnets imported yet.
        <br />
        Upload a CSV to get started.
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {/* Filter input */}
      <div className="px-2 py-1.5">
        <input
          type="text"
          placeholder="Filter by name or CIDR..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full px-2 py-1 text-xs bg-[#0f2023] border border-[#1e3a40] rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
        />
      </div>
      {/* Tree header */}
      <div className="px-2 py-1 text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
        Display Name
      </div>
      {filteredTree.map((node) => (
        <TreeNode
          key={node.id}
          node={node}
          depth={0}
          selectedSubnetId={selectedSubnetId}
          onSelectSubnet={onSelectSubnet}
          onSelectNode={onSelectNode}
          onContextMenu={onContextMenu}
          filter={filter}
        />
      ))}
    </div>
  );
}
