import React from 'react';

// Matches @[kind:namespace/name] or @[kind:name]
const RESOURCE_REF_REGEX = /@\[([a-z_]+):(?:([a-z0-9][a-z0-9._-]*)\/)?([a-z0-9][a-z0-9._-]*)\]/gi;

interface ResourceEntityInlineProps {
  kind: string;
  name: string;
  namespace: string | null;
  onClick?: (kind: string, name: string, namespace: string | null) => void;
}

const KIND_ICONS: Record<string, string> = {
  pod: 'deployed_code',
  deployment: 'layers',
  service: 'router',
  node: 'dns',
  configmap: 'settings',
  pvc: 'storage',
  ingress: 'language',
  route: 'language',
  namespace: 'folder',
  deploymentconfig: 'swap_horiz',
  replicaset: 'layers',
  secret: 'lock',
  statefulset: 'layers',
};

const ResourceEntityInline: React.FC<ResourceEntityInlineProps> = ({ kind, name, namespace, onClick }) => {
  const icon = KIND_ICONS[kind] || 'deployed_code';

  return (
    <button
      type="button"
      onClick={() => onClick?.(kind, name, namespace)}
      className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-cyan-400
                 border-b border-dashed border-cyan-500/40 hover:bg-cyan-950/30
                 hover:border-cyan-400/60 transition-colors cursor-pointer"
      title={`${kind}: ${namespace ? `${namespace}/` : ''}${name}`}
    >
      <span
        className="text-[11px] text-cyan-500/80"
        style={{ fontFamily: 'Material Symbols Outlined' }}
      >
        {icon}
      </span>
      <span className="text-[11px] font-mono">{name}</span>
    </button>
  );
};

/**
 * Parse text containing @[kind:namespace/name] tokens into React elements.
 *
 * @param text - Text to parse (e.g., "Pod @[pod:ns/auth-5b6q] is crashing")
 * @param onEntityClick - Callback when a resource entity is clicked
 * @param defaultNamespace - Fallback namespace for short-form @[kind:name]
 * @returns Array of React nodes (strings and ResourceEntityInline components)
 */
export function parseResourceEntities(
  text: string,
  onEntityClick?: (kind: string, name: string, namespace: string | null) => void,
  defaultNamespace?: string | null,
): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;

  // Reset regex state
  RESOURCE_REF_REGEX.lastIndex = 0;

  let match: RegExpExecArray | null;
  while ((match = RESOURCE_REF_REGEX.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const kind = match[1].toLowerCase();
    const namespace = match[2] || defaultNamespace || null;
    const name = match[3];

    nodes.push(
      <ResourceEntityInline
        key={`${kind}-${namespace}-${name}-${match.index}`}
        kind={kind}
        name={name}
        namespace={namespace}
        onClick={onEntityClick}
      />
    );

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes.length > 0 ? nodes : [text];
}
