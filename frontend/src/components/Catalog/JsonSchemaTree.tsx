import React, { useState } from 'react';

interface Props {
  schema: Record<string, unknown>;
  depth?: number;
}

const JsonSchemaTree: React.FC<Props> = ({ schema, depth = 0 }) => {
  const properties = (schema.properties ?? {}) as Record<string, any>;
  const required = (schema.required ?? []) as string[];
  const entries = Object.entries(properties);

  if (entries.length === 0) {
    return <div className="text-xs text-wr-muted italic">No fields declared.</div>;
  }

  return (
    <ul className={depth === 0 ? '' : 'pl-4 border-l border-wr-border'}>
      {entries.map(([name, prop]) => (
        <FieldRow
          key={name}
          name={name}
          prop={prop}
          required={required.includes(name)}
          depth={depth}
        />
      ))}
    </ul>
  );
};

const FieldRow: React.FC<{
  name: string;
  prop: any;
  required: boolean;
  depth: number;
}> = ({ name, prop, required, depth }) => {
  const [open, setOpen] = useState(depth === 0);
  const hasNested = prop && prop.type === 'object' && prop.properties;

  return (
    <li className="py-1">
      <div className="flex items-center gap-2 text-sm">
        {hasNested ? (
          <button
            onClick={() => setOpen(!open)}
            className="text-wr-muted"
            aria-expanded={open}
          >
            {open ? '▾' : '▸'}
          </button>
        ) : (
          <span className="w-3" />
        )}
        <span className="text-wr-text font-medium">{name}</span>
        <span className="text-wr-muted text-xs">{prop?.type ?? 'any'}</span>
        {required && <span className="text-amber-400 text-xs">required</span>}
        {prop?.description && (
          <span className="text-wr-muted text-xs">— {prop.description}</span>
        )}
      </div>
      {hasNested && open && <JsonSchemaTree schema={prop} depth={depth + 1} />}
    </li>
  );
};

export default JsonSchemaTree;
