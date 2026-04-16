import { useCallback, useEffect, useMemo, useState } from 'react';
import Ajv from 'ajv';
import { isSchemaSimple, SchemaField } from '../Shared/SchemaField';

type AnySchema = Record<string, unknown>;

export interface InputsFormProps {
  schema: AnySchema; // JSON Schema object
  onSubmit(inputs: Record<string, unknown>, opts: { idempotency_key?: string }): void;
  onCancel(): void;
  persistKey?: string; // localStorage key for prefill
  serverErrors?: string[];
}

/** Build an empty default object from a JSON Schema's properties. */
function defaultFromSchema(schema: AnySchema): Record<string, unknown> {
  const props = (schema.properties ?? {}) as Record<string, AnySchema>;
  const result: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(props)) {
    if (prop.default !== undefined) {
      result[key] = prop.default;
    }
  }
  return result;
}

/** Determine if every top-level property is simple (renders as form fields). */
function allPropertiesSimple(schema: AnySchema): boolean {
  const props = (schema.properties ?? {}) as Record<string, unknown>;
  for (const prop of Object.values(props)) {
    if (!isSchemaSimple(prop)) return false;
  }
  return true;
}

export function InputsForm({
  schema,
  onSubmit,
  onCancel,
  persistKey,
  serverErrors,
}: InputsFormProps) {
  const isSimple = useMemo(() => allPropertiesSimple(schema), [schema]);

  // Mode: 'form' or 'json'
  const [mode, setMode] = useState<'form' | 'json'>(isSimple ? 'form' : 'json');

  // Form values (object)
  const [formValues, setFormValues] = useState<Record<string, unknown>>(() => {
    if (persistKey) {
      try {
        const stored = window.localStorage.getItem(persistKey);
        if (stored) return JSON.parse(stored);
      } catch {
        // ignore
      }
    }
    return defaultFromSchema(schema);
  });

  // JSON text
  const [jsonText, setJsonText] = useState(() =>
    JSON.stringify(formValues, null, 2),
  );
  const [jsonParseError, setJsonParseError] = useState<string | null>(null);

  // Idempotency key
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [moreOpen, setMoreOpen] = useState(false);

  // AJV validation
  const ajv = useMemo(() => new Ajv({ allErrors: true }), []);
  const validate = useMemo(() => {
    try {
      return ajv.compile(schema);
    } catch {
      return null;
    }
  }, [ajv, schema]);

  // Compute current parsed values
  const currentValues = useMemo<Record<string, unknown> | null>(() => {
    if (mode === 'form') return formValues;
    try {
      const parsed = JSON.parse(jsonText);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))
        return null;
      return parsed as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [mode, formValues, jsonText]);

  // Validate
  const validationErrors = useMemo<string[]>(() => {
    if (!currentValues || !validate) return ['Invalid input'];
    const valid = validate(currentValues);
    if (valid) return [];
    return (validate.errors ?? []).map(
      (e) => `${e.instancePath || '/'} ${e.message ?? 'invalid'}`,
    );
  }, [currentValues, validate]);

  const isValid = currentValues !== null && validationErrors.length === 0;

  // Sync json text when switching from form to json
  const switchToJson = useCallback(() => {
    setJsonText(JSON.stringify(formValues, null, 2));
    setJsonParseError(null);
    setMode('json');
  }, [formValues]);

  // Sync form values when switching from json to form
  const switchToForm = useCallback(() => {
    try {
      const parsed = JSON.parse(jsonText);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setJsonParseError('JSON must be an object');
        return;
      }
      setFormValues(parsed as Record<string, unknown>);
      setJsonParseError(null);
      setMode('form');
    } catch (e) {
      setJsonParseError(e instanceof Error ? e.message : 'Invalid JSON');
    }
  }, [jsonText]);

  // Handle json text changes
  const handleJsonChange = useCallback(
    (text: string) => {
      setJsonText(text);
      try {
        JSON.parse(text);
        setJsonParseError(null);
      } catch (e) {
        setJsonParseError(e instanceof Error ? e.message : 'Invalid JSON');
      }
    },
    [],
  );

  // Update json text when form values change in form mode
  useEffect(() => {
    if (mode === 'form') {
      setJsonText(JSON.stringify(formValues, null, 2));
    }
  }, [mode, formValues]);

  // Submit handler
  const handleSubmit = useCallback(() => {
    if (!isValid || !currentValues) return;
    if (persistKey) {
      window.localStorage.setItem(persistKey, JSON.stringify(currentValues));
    }
    onSubmit(currentValues, {
      idempotency_key: idempotencyKey || undefined,
    });
  }, [isValid, currentValues, persistKey, onSubmit, idempotencyKey]);

  // Required fields list
  const requiredFields = useMemo(
    () => (Array.isArray(schema.required) ? (schema.required as string[]) : []),
    [schema],
  );

  const properties = (schema.properties ?? {}) as Record<string, AnySchema>;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      data-testid="inputs-form-modal"
    >
      <div className="relative w-full max-w-lg rounded-lg border border-wr-border bg-wr-surface shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-wr-border px-4 py-3">
          <h2 className="text-sm font-medium text-wr-text">Run Workflow</h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="text-wr-text-muted hover:text-wr-text"
          >
            &times;
          </button>
        </div>

        {/* Mode toggle */}
        <div className="flex border-b border-wr-border">
          <button
            type="button"
            onClick={mode === 'json' ? switchToForm : undefined}
            aria-label="Form view"
            className={`flex-1 px-4 py-2 text-xs font-medium ${
              mode === 'form'
                ? 'border-b-2 border-wr-accent text-wr-accent'
                : 'text-wr-text-muted hover:text-wr-text'
            }`}
          >
            Form view
          </button>
          <button
            type="button"
            onClick={mode === 'form' ? switchToJson : undefined}
            aria-label="JSON view"
            className={`flex-1 px-4 py-2 text-xs font-medium ${
              mode === 'json'
                ? 'border-b-2 border-wr-accent text-wr-accent'
                : 'text-wr-text-muted hover:text-wr-text'
            }`}
          >
            JSON view
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[60vh] overflow-y-auto p-4">
          {/* Server errors */}
          {serverErrors && serverErrors.length > 0 && (
            <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-400">
              {serverErrors.map((err, i) => (
                <div key={i}>{err}</div>
              ))}
            </div>
          )}

          {mode === 'form' ? (
            <div className="flex flex-col gap-3">
              {Object.entries(properties).map(([key, propSchema]) => (
                <SchemaField
                  key={key}
                  name={key}
                  schema={propSchema}
                  value={formValues[key]}
                  required={requiredFields.includes(key)}
                  path={key}
                  onChange={(v) => {
                    setFormValues((prev) => {
                      const next = { ...prev };
                      if (v === undefined) {
                        delete next[key];
                      } else {
                        next[key] = v;
                      }
                      return next;
                    });
                  }}
                  onRequestJsonMode={switchToJson}
                />
              ))}
              {/* Form mode validation errors */}
              {validationErrors.length > 0 && (
                <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-400">
                  {validationErrors.map((err, i) => (
                    <div key={i}>{err}</div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <textarea
                aria-label="JSON input"
                value={jsonText}
                onChange={(e) => handleJsonChange(e.target.value)}
                className="h-48 w-full rounded-md border border-wr-border bg-wr-bg p-2 font-mono text-sm text-wr-text"
                spellCheck={false}
              />
              {jsonParseError && (
                <div className="text-xs text-red-400">{jsonParseError}</div>
              )}
              {!jsonParseError && validationErrors.length > 0 && (
                <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-400">
                  {validationErrors.map((err, i) => (
                    <div key={i}>{err}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* More options */}
          <div className="mt-4 border-t border-wr-border pt-3">
            <button
              type="button"
              onClick={() => setMoreOpen((o) => !o)}
              className="text-xs text-wr-text-muted hover:text-wr-text"
            >
              {moreOpen ? '▾' : '▸'} More options
            </button>
            {moreOpen && (
              <div className="mt-2">
                <label
                  htmlFor="idempotency-key"
                  className="block text-xs font-medium text-wr-text-muted"
                >
                  Idempotency key
                </label>
                <input
                  id="idempotency-key"
                  type="text"
                  aria-label="Idempotency key"
                  value={idempotencyKey}
                  onChange={(e) => setIdempotencyKey(e.target.value)}
                  className="mt-1 w-full rounded-md border border-wr-border bg-wr-bg px-2 py-1.5 text-sm text-wr-text"
                  placeholder="Optional"
                />
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-wr-border px-4 py-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-wr-border bg-wr-surface px-3 py-1.5 text-sm text-wr-text hover:bg-wr-elevated"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!isValid}
            onClick={handleSubmit}
            className="rounded-md bg-wr-accent px-3 py-1.5 text-sm text-wr-on-accent hover:bg-wr-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Run workflow
          </button>
        </div>
      </div>
    </div>
  );
}

export default InputsForm;
