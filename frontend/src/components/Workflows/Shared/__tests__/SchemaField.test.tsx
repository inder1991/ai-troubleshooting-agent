import { describe, expect, test, vi } from 'vitest';
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SchemaField, isSchemaSimple } from '../SchemaField';

/**
 * Controlled wrapper — keeps `value` in local state so keystrokes
 * accumulate the way they do in real usage.
 */
function Controlled({
  schema,
  initial,
  onChange,
  name = 'f',
  required,
}: {
  schema: any;
  initial: unknown;
  onChange: (v: unknown) => void;
  name?: string;
  required?: boolean;
}) {
  const [v, setV] = useState(initial);
  return (
    <SchemaField
      name={name}
      schema={schema}
      value={v}
      required={required}
      onChange={(nv) => {
        setV(nv);
        onChange(nv);
      }}
    />
  );
}

describe('isSchemaSimple', () => {
  test('returns true for supported primitive types', () => {
    expect(isSchemaSimple({ type: 'string' })).toBe(true);
    expect(isSchemaSimple({ type: 'string', enum: ['a', 'b'] })).toBe(true);
    expect(isSchemaSimple({ type: 'string', format: 'date-time' })).toBe(true);
    expect(isSchemaSimple({ type: 'integer' })).toBe(true);
    expect(isSchemaSimple({ type: 'number' })).toBe(true);
    expect(isSchemaSimple({ type: 'boolean' })).toBe(true);
  });

  test('returns false for array', () => {
    expect(isSchemaSimple({ type: 'array', items: { type: 'string' } })).toBe(
      false,
    );
  });

  test('returns false for oneOf/anyOf/allOf', () => {
    expect(isSchemaSimple({ oneOf: [{ type: 'string' }] })).toBe(false);
    expect(isSchemaSimple({ anyOf: [{ type: 'string' }] })).toBe(false);
    expect(isSchemaSimple({ allOf: [{ type: 'string' }] })).toBe(false);
  });

  test('returns true for object of depth <= 2', () => {
    expect(
      isSchemaSimple({
        type: 'object',
        properties: { a: { type: 'string' } },
      }),
    ).toBe(true);
    expect(
      isSchemaSimple({
        type: 'object',
        properties: {
          a: {
            type: 'object',
            properties: { b: { type: 'string' } },
          },
        },
      }),
    ).toBe(true);
  });

  test('returns false for object of depth > 2', () => {
    expect(
      isSchemaSimple({
        type: 'object',
        properties: {
          a: {
            type: 'object',
            properties: {
              b: {
                type: 'object',
                properties: { c: { type: 'string' } },
              },
            },
          },
        },
      }),
    ).toBe(false);
  });
});

describe('SchemaField', () => {
  test('renders text input for string and emits typed value', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Controlled
        name="title"
        schema={{ type: 'string', description: 'A title' }}
        initial=""
        onChange={onChange}
      />,
    );
    const input = screen.getByLabelText('title') as HTMLInputElement;
    expect(input.type).toBe('text');
    expect(screen.getByText('A title')).toBeInTheDocument();
    await user.type(input, 'abc');
    expect(onChange).toHaveBeenLastCalledWith('abc');
  });

  test('renders select for string enum', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SchemaField
        name="color"
        schema={{ type: 'string', enum: ['red', 'blue'] }}
        value=""
        onChange={onChange}
      />,
    );
    const select = screen.getByLabelText('color') as HTMLSelectElement;
    expect(select.tagName).toBe('SELECT');
    await user.selectOptions(select, 'blue');
    expect(onChange).toHaveBeenLastCalledWith('blue');
  });

  test('renders datetime-local for format:date-time and round-trips', () => {
    const onChange = vi.fn();
    const iso = '2026-04-16T10:30:00.000Z';
    render(
      <SchemaField
        name="startedAt"
        schema={{ type: 'string', format: 'date-time' }}
        value={iso}
        onChange={onChange}
      />,
    );
    const input = screen.getByLabelText('startedAt') as HTMLInputElement;
    expect(input.type).toBe('datetime-local');
    // Value should be a local-time representation (no Z suffix).
    expect(input.value).not.toBe('');
    expect(input.value.endsWith('Z')).toBe(false);
  });

  test('number input: empty emits undefined, non-empty emits number', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { unmount } = render(
      <Controlled
        name="count"
        schema={{ type: 'number' }}
        initial={42}
        onChange={onChange}
      />,
    );
    const input = screen.getByLabelText('count') as HTMLInputElement;
    expect(input.type).toBe('number');
    await user.clear(input);
    expect(onChange).toHaveBeenLastCalledWith(undefined);
    unmount();

    const onChange2 = vi.fn();
    render(
      <Controlled
        name="count"
        schema={{ type: 'number' }}
        initial={undefined}
        onChange={onChange2}
      />,
    );
    await user.type(screen.getByLabelText('count'), '3.5');
    expect(onChange2).toHaveBeenLastCalledWith(3.5);
  });

  test('integer input parses to int', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Controlled
        name="n"
        schema={{ type: 'integer' }}
        initial={undefined}
        onChange={onChange}
      />,
    );
    await user.type(screen.getByLabelText('n'), '7');
    expect(onChange).toHaveBeenLastCalledWith(7);
  });

  test('boolean checkbox toggles', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SchemaField
        name="enabled"
        schema={{ type: 'boolean' }}
        value={false}
        onChange={onChange}
      />,
    );
    const cb = screen.getByLabelText('enabled') as HTMLInputElement;
    expect(cb.type).toBe('checkbox');
    await user.click(cb);
    expect(onChange).toHaveBeenLastCalledWith(true);
  });

  test('renders fieldset for flat object and composes child onChange', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Controlled
        name="user"
        schema={{
          type: 'object',
          properties: {
            name: { type: 'string' },
            age: { type: 'integer' },
          },
        }}
        initial={{ name: 'ada', age: 30 }}
        onChange={onChange}
      />,
    );
    // fieldset with legend=name of parent field
    expect(screen.getByRole('group', { name: /user/i })).toBeInTheDocument();
    const nameInput = screen.getByLabelText('name') as HTMLInputElement;
    expect(nameInput.value).toBe('ada');
    await user.clear(nameInput);
    await user.type(nameInput, 'bob');
    // The last call should carry both fields, with name now updated.
    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last).toEqual({ name: 'bob', age: 30 });
  });

  test('required badge is shown when required=true', () => {
    render(
      <SchemaField
        name="title"
        schema={{ type: 'string' }}
        value=""
        onChange={vi.fn()}
        required
      />,
    );
    expect(screen.getByText(/required/i)).toBeInTheDocument();
  });

  test('renders JSON mode callout for unsupported schema (oneOf)', () => {
    render(
      <SchemaField
        name="mixed"
        schema={{ oneOf: [{ type: 'string' }, { type: 'number' }] }}
        value={null}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/json mode/i)).toBeInTheDocument();
  });

  test('renders JSON mode callout for array', () => {
    render(
      <SchemaField
        name="tags"
        schema={{ type: 'array', items: { type: 'string' } }}
        value={[]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/json mode/i)).toBeInTheDocument();
  });
});
