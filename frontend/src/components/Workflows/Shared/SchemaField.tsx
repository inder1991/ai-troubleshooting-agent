import { useId } from 'react';

type AnySchema = Record<string, unknown>;

/**
 * Pure helper. Returns true iff every node of the schema is a supported
 * primitive (string/integer/number/boolean, optional enum, optional
 * format:date-time), or an object whose total nested-object depth is ≤ 2.
 *
 * Root is depth 0, object-within-root is depth 1, object-within-object is
 * depth 2 (still simple). Deeper, arrays, oneOf/anyOf/allOf, or any
 * unrecognised type yields false.
 */
export function isSchemaSimple(schema: unknown, depth = 0): boolean {
  if (!schema || typeof schema !== 'object') return false;
  const s = schema as AnySchema;
  if ('oneOf' in s || 'anyOf' in s || 'allOf' in s) return false;
  const t = s.type;
  if (t === 'string' || t === 'integer' || t === 'number' || t === 'boolean') {
    return true;
  }
  if (t === 'object') {
    if (depth >= 2) return false;
    const props = (s.properties as Record<string, unknown> | undefined) ?? {};
    for (const p of Object.values(props)) {
      if (!isSchemaSimple(p, depth + 1)) return false;
    }
    return true;
  }
  return false;
}

interface Props {
  name: string;
  schema: AnySchema;
  value: unknown;
  onChange: (v: unknown) => void;
  required?: boolean;
  path?: string;
  onRequestJsonMode?: () => void;
}

const baseInput =
  'w-full rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text';

function Description({ text }: { text?: unknown }) {
  if (!text || typeof text !== 'string') return null;
  return <p className="mt-1 text-xs text-wr-text-muted">{text}</p>;
}

function LabelRow({
  htmlFor,
  name,
  required,
}: {
  htmlFor: string;
  name: string;
  required?: boolean;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="flex items-center gap-2 text-xs font-medium text-wr-text-muted"
    >
      <span>{name}</span>
      {required && (
        <span className="rounded bg-wr-accent/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-wr-accent">
          required
        </span>
      )}
    </label>
  );
}

/** Convert ISO string to a "YYYY-MM-DDTHH:mm" local value for datetime-local. */
function isoToLocal(iso: unknown): string {
  if (typeof iso !== 'string' || !iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

function localToIso(local: string): string | undefined {
  if (!local) return undefined;
  const d = new Date(local);
  if (Number.isNaN(d.getTime())) return undefined;
  return d.toISOString();
}

export function SchemaField({
  name,
  schema,
  value,
  onChange,
  required,
  path,
  onRequestJsonMode,
}: Props) {
  const autoId = useId();
  const id = path ? `sf-${path}` : `sf-${autoId}-${name}`;

  if (!isSchemaSimple(schema)) {
    return (
      <div className="rounded-md border border-wr-border bg-wr-elevated p-3 text-sm text-wr-text">
        <div className="font-medium text-wr-text">{name}</div>
        <div className="mt-1 text-xs text-wr-text-muted">
          This field requires JSON mode.
        </div>
        {onRequestJsonMode && (
          <button
            type="button"
            onClick={onRequestJsonMode}
            className="mt-2 rounded-md border border-wr-border bg-wr-surface px-2 py-1 text-xs text-wr-accent hover:bg-wr-elevated"
          >
            Switch to JSON mode
          </button>
        )}
      </div>
    );
  }

  const s = schema;
  const t = s.type as string;
  const desc = s.description;
  const examples = Array.isArray(s.examples) ? (s.examples as unknown[]) : null;
  const placeholder =
    examples && examples.length > 0 ? String(examples[0]) : undefined;

  // string + enum
  if (t === 'string' && Array.isArray(s.enum)) {
    const opts = s.enum as unknown[];
    return (
      <div>
        <LabelRow htmlFor={id} name={name} required={required} />
        <select
          id={id}
          aria-label={name}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
          className={baseInput}
        >
          <option value="">(select)</option>
          {opts.map((o) => (
            <option key={String(o)} value={String(o)}>
              {String(o)}
            </option>
          ))}
        </select>
        <Description text={desc} />
      </div>
    );
  }

  // string + format: date-time
  if (t === 'string' && s.format === 'date-time') {
    return (
      <div>
        <LabelRow htmlFor={id} name={name} required={required} />
        <input
          id={id}
          type="datetime-local"
          aria-label={name}
          value={isoToLocal(value)}
          onChange={(e) => {
            const iso = localToIso(e.target.value);
            onChange(iso);
          }}
          className={baseInput}
        />
        <Description text={desc} />
      </div>
    );
  }

  // plain string
  if (t === 'string') {
    return (
      <div>
        <LabelRow htmlFor={id} name={name} required={required} />
        <input
          id={id}
          type="text"
          aria-label={name}
          value={(value as string) ?? ''}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className={baseInput}
        />
        <Description text={desc} />
      </div>
    );
  }

  if (t === 'integer' || t === 'number') {
    const step = t === 'integer' ? 1 : 'any';
    return (
      <div>
        <LabelRow htmlFor={id} name={name} required={required} />
        <input
          id={id}
          type="number"
          aria-label={name}
          step={step}
          value={
            typeof value === 'number' && !Number.isNaN(value)
              ? (value as number)
              : ''
          }
          placeholder={placeholder}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '') {
              onChange(undefined);
              return;
            }
            const n = t === 'integer' ? parseInt(raw, 10) : parseFloat(raw);
            if (Number.isNaN(n)) {
              onChange(undefined);
              return;
            }
            onChange(n);
          }}
          className={baseInput}
        />
        <Description text={desc} />
      </div>
    );
  }

  if (t === 'boolean') {
    return (
      <div>
        <label
          htmlFor={id}
          className="inline-flex items-center gap-2 text-sm text-wr-text"
        >
          <input
            id={id}
            type="checkbox"
            aria-label={name}
            checked={value === true}
            onChange={(e) => onChange(e.target.checked)}
            className="accent-wr-accent"
          />
          <span className="text-xs font-medium text-wr-text-muted">{name}</span>
          {required && (
            <span className="rounded bg-wr-accent/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-wr-accent">
              required
            </span>
          )}
        </label>
        <Description text={desc} />
      </div>
    );
  }

  if (t === 'object') {
    const props = (s.properties as Record<string, AnySchema> | undefined) ?? {};
    const reqList = Array.isArray(s.required) ? (s.required as string[]) : [];
    const obj = (value && typeof value === 'object' ? value : {}) as Record<
      string,
      unknown
    >;
    return (
      <fieldset
        aria-label={name}
        className="rounded-md border border-wr-border bg-wr-surface p-3"
      >
        <legend className="px-1 text-xs font-medium text-wr-text-muted">
          {name}
          {required && (
            <span className="ml-2 rounded bg-wr-accent/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-wr-accent">
              required
            </span>
          )}
        </legend>
        <Description text={desc} />
        <div className="mt-2 flex flex-col gap-3">
          {Object.entries(props).map(([key, childSchema]) => (
            <SchemaField
              key={key}
              name={key}
              schema={childSchema}
              value={obj[key]}
              required={reqList.includes(key)}
              path={path ? `${path}.${key}` : key}
              onChange={(nv) => {
                const next = { ...obj };
                if (nv === undefined) {
                  delete next[key];
                } else {
                  next[key] = nv;
                }
                onChange(next);
              }}
              onRequestJsonMode={onRequestJsonMode}
            />
          ))}
        </div>
      </fieldset>
    );
  }

  // Shouldn't reach: isSchemaSimple allowed it but handler missing.
  return (
    <div className="rounded-md border border-wr-border bg-wr-elevated p-3 text-xs text-wr-text-muted">
      Unsupported widget for {name}.
    </div>
  );
}

export default SchemaField;
