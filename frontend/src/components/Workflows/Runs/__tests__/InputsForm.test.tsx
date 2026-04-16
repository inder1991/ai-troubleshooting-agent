import { describe, expect, test, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InputsForm } from '../InputsForm';

// Mock localStorage since jsdom doesn't provide full implementation
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
    get length() { return Object.keys(store).length; },
    key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
});

// Simple schema — all top-level props are simple primitives
const simpleSchema = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    count: { type: 'integer' },
  },
  required: ['name'],
};

// Complex schema — has oneOf, so should default to JSON mode
const complexSchema = {
  type: 'object',
  properties: {
    config: {
      oneOf: [
        { type: 'string' },
        { type: 'object', properties: { url: { type: 'string' } } },
      ],
    },
  },
};

describe('InputsForm', () => {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();

  beforeEach(() => {
    onSubmit.mockReset();
    onCancel.mockReset();
    localStorageMock.clear();
    localStorageMock.getItem.mockClear();
    localStorageMock.setItem.mockClear();
  });

  test('form mode: renders SchemaField for each property in a simple schema', () => {
    render(
      <InputsForm schema={simpleSchema} onSubmit={onSubmit} onCancel={onCancel} />,
    );

    // Should default to Form view for simple schema
    expect(screen.getByRole('button', { name: /form view/i })).toBeInTheDocument();

    // SchemaField renders labeled inputs for each property
    expect(screen.getByLabelText('name')).toBeInTheDocument();
    expect(screen.getByLabelText('count')).toBeInTheDocument();
  });

  test('JSON mode: renders textarea for a complex schema', () => {
    render(
      <InputsForm schema={complexSchema} onSubmit={onSubmit} onCancel={onCancel} />,
    );

    // Should default to JSON view for complex schema
    const textarea = screen.getByRole('textbox', { name: /json input/i });
    expect(textarea).toBeInTheDocument();
    expect(textarea.tagName).toBe('TEXTAREA');
  });

  test('toggle: form to JSON serializes current values', async () => {
    const user = userEvent.setup();
    render(
      <InputsForm schema={simpleSchema} onSubmit={onSubmit} onCancel={onCancel} />,
    );

    // Fill in a value
    const nameInput = screen.getByLabelText('name');
    await user.type(nameInput, 'hello');

    // Switch to JSON view
    await user.click(screen.getByRole('button', { name: /json view/i }));

    // Textarea should contain the serialized form values
    const textarea = screen.getByRole('textbox', { name: /json input/i });
    const parsed = JSON.parse((textarea as HTMLTextAreaElement).value);
    expect(parsed.name).toBe('hello');
  });

  test('toggle: JSON to form populates fields from JSON text', async () => {
    const user = userEvent.setup();
    render(
      <InputsForm schema={simpleSchema} onSubmit={onSubmit} onCancel={onCancel} />,
    );

    // Switch to JSON view
    await user.click(screen.getByRole('button', { name: /json view/i }));

    const textarea = screen.getByRole('textbox', { name: /json input/i });
    await user.clear(textarea);
    await user.type(textarea, '{{"name":"world","count":5}');

    // Switch back to Form view
    await user.click(screen.getByRole('button', { name: /form view/i }));

    // Form fields should be populated
    expect(screen.getByLabelText('name')).toHaveValue('world');
    expect(screen.getByLabelText('count')).toHaveValue(5);
  });

  test('validation: submit disabled when AJV validation fails; error messages shown', async () => {
    const user = userEvent.setup();
    render(
      <InputsForm schema={simpleSchema} onSubmit={onSubmit} onCancel={onCancel} />,
    );

    // Don't fill required 'name' field — submit should be disabled
    const submitBtn = screen.getByRole('button', { name: /run workflow/i });
    expect(submitBtn).toBeDisabled();

    // Fill the required field
    await user.type(screen.getByLabelText('name'), 'valid');

    // Submit should now be enabled
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /run workflow/i })).toBeEnabled();
    });
  });

  test('localStorage: prefills from localStorage when persistKey provided', () => {
    const key = 'test-persist-key';
    window.localStorage.setItem(key, JSON.stringify({ name: 'prefilled', count: 42 }));

    render(
      <InputsForm
        schema={simpleSchema}
        onSubmit={onSubmit}
        onCancel={onCancel}
        persistKey={key}
      />,
    );

    expect(screen.getByLabelText('name')).toHaveValue('prefilled');
    expect(screen.getByLabelText('count')).toHaveValue(42);
  });

  test('submit: calls onSubmit with validated inputs + idempotency_key', async () => {
    const user = userEvent.setup();
    render(
      <InputsForm schema={simpleSchema} onSubmit={onSubmit} onCancel={onCancel} />,
    );

    await user.type(screen.getByLabelText('name'), 'test');

    // Open "More options" and add idempotency key
    await user.click(screen.getByText(/more options/i));
    const idemInput = screen.getByLabelText(/idempotency/i);
    await user.type(idemInput, 'key-123');

    await user.click(screen.getByRole('button', { name: /run workflow/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'test' }),
      { idempotency_key: 'key-123' },
    );
  });

  test('cancel: calls onCancel', async () => {
    const user = userEvent.setup();
    render(
      <InputsForm schema={simpleSchema} onSubmit={onSubmit} onCancel={onCancel} />,
    );

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  test('close (x) button calls onCancel', async () => {
    const user = userEvent.setup();
    render(
      <InputsForm schema={simpleSchema} onSubmit={onSubmit} onCancel={onCancel} />,
    );

    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  test('serverErrors are displayed', () => {
    render(
      <InputsForm
        schema={simpleSchema}
        onSubmit={onSubmit}
        onCancel={onCancel}
        serverErrors={['Input validation failed on server']}
      />,
    );

    expect(screen.getByText('Input validation failed on server')).toBeInTheDocument();
  });

  test('localStorage: saves on successful submit', async () => {
    const key = 'test-save-key';
    const user = userEvent.setup();
    render(
      <InputsForm
        schema={simpleSchema}
        onSubmit={onSubmit}
        onCancel={onCancel}
        persistKey={key}
      />,
    );

    await user.type(screen.getByLabelText('name'), 'saved-value');
    await user.click(screen.getByRole('button', { name: /run workflow/i }));

    const stored = JSON.parse(window.localStorage.getItem(key)!);
    expect(stored.name).toBe('saved-value');
  });
});
