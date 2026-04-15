import { describe, expect, test } from 'vitest';
import { listPaths } from '../schemaPaths';

describe('listPaths', () => {
  test('returns empty list for non-object schema', () => {
    expect(listPaths(null)).toEqual([]);
    expect(listPaths(undefined)).toEqual([]);
    expect(listPaths(42 as unknown as object)).toEqual([]);
  });

  test('lists top-level properties', () => {
    const schema = {
      type: 'object',
      properties: {
        name: { type: 'string' },
        count: { type: 'integer' },
      },
    };
    expect(listPaths(schema).sort()).toEqual(['count', 'name']);
  });

  test('recurses into nested object properties', () => {
    const schema = {
      type: 'object',
      properties: {
        user: {
          type: 'object',
          properties: {
            name: { type: 'string' },
            age: { type: 'integer' },
          },
        },
      },
    };
    const paths = listPaths(schema);
    expect(paths).toContain('user');
    expect(paths).toContain('user.name');
    expect(paths).toContain('user.age');
  });

  test('recurses into array items with [*] marker', () => {
    const schema = {
      type: 'object',
      properties: {
        items: {
          type: 'array',
          items: {
            type: 'object',
            properties: { id: { type: 'string' } },
          },
        },
      },
    };
    const paths = listPaths(schema);
    expect(paths).toContain('items');
    expect(paths).toContain('items[*].id');
  });

  test('applies prefix argument', () => {
    const schema = {
      type: 'object',
      properties: { x: { type: 'string' } },
    };
    expect(listPaths(schema, 'out')).toEqual(['out.x']);
  });
});
