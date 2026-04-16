import { afterAll, afterEach, beforeAll, describe, expect, test } from 'vitest';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import {
  listWorkflows,
  getWorkflow,
  createWorkflow,
  listVersions,
  getVersion,
  createVersion,
  WorkflowsDisabledError,
  CompileError,
} from '../workflows';

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('services/workflows', () => {
  test('listWorkflows returns array', async () => {
    server.use(
      http.get('*/api/v4/workflows', () =>
        HttpResponse.json({
          workflows: [
            {
              id: 'w1',
              name: 'x',
              description: '',
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
        }),
      ),
    );
    const result = await listWorkflows();
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('w1');
  });

  test('listWorkflows 404 throws WorkflowsDisabledError', async () => {
    server.use(
      http.get('*/api/v4/workflows', () => new HttpResponse(null, { status: 404 })),
    );
    await expect(listWorkflows()).rejects.toBeInstanceOf(WorkflowsDisabledError);
  });

  test('getWorkflow returns detail', async () => {
    server.use(
      http.get('*/api/v4/workflows/w1', () =>
        HttpResponse.json({
          id: 'w1',
          name: 'n',
          description: '',
          created_at: '2026-01-01T00:00:00Z',
        }),
      ),
    );
    const r = await getWorkflow('w1');
    expect(r.id).toBe('w1');
  });

  test('createWorkflow POSTs body and returns detail', async () => {
    let sawBody: any = null;
    server.use(
      http.post('*/api/v4/workflows', async ({ request }) => {
        sawBody = await request.json();
        return HttpResponse.json(
          {
            id: 'w2',
            name: sawBody.name,
            description: sawBody.description,
            created_at: '2026-01-01T00:00:00Z',
          },
          { status: 201 },
        );
      }),
    );
    const r = await createWorkflow({ name: 'nn', description: 'dd' });
    expect(r.id).toBe('w2');
    expect(sawBody).toEqual({ name: 'nn', description: 'dd' });
  });

  test('listVersions returns array', async () => {
    server.use(
      http.get('*/api/v4/workflows/w1/versions', () =>
        HttpResponse.json({
          versions: [
            {
              version_id: 'v2',
              workflow_id: 'w1',
              version: 2,
              created_at: '2026-04-02T00:00:00Z',
            },
            {
              version_id: 'v1',
              workflow_id: 'w1',
              version: 1,
              created_at: '2026-04-01T00:00:00Z',
            },
          ],
        }),
      ),
    );
    const r = await listVersions('w1');
    expect(r).toHaveLength(2);
    expect(r[0].version).toBe(2);
  });

  test('getVersion returns version detail', async () => {
    server.use(
      http.get('*/api/v4/workflows/w1/versions/3', () =>
        HttpResponse.json({
          workflow_id: 'w1',
          version: 3,
          created_at: '2026-04-03T00:00:00Z',
          dag: { inputs_schema: {}, steps: [] },
          compiled: {},
        }),
      ),
    );
    const r = await getVersion('w1', 3);
    expect(r.version).toBe(3);
  });

  test('createVersion 422 throws CompileError with path', async () => {
    server.use(
      http.post('*/api/v4/workflows/w1/versions', () =>
        HttpResponse.json(
          {
            detail: {
              type: 'compile_error',
              message: 'unknown agent',
              path: 'steps[0].agent',
            },
          },
          { status: 422 },
        ),
      ),
    );
    try {
      await createVersion('w1', { inputs_schema: {}, steps: [] });
      throw new Error('should not reach');
    } catch (e: any) {
      expect(e).toBeInstanceOf(CompileError);
      expect(e.type).toBe('compile_error');
      expect(e.path).toBe('steps[0].agent');
      expect(e.message).toBe('unknown agent');
    }
  });

  test('createVersion 201 returns VersionSummary', async () => {
    server.use(
      http.post('*/api/v4/workflows/w1/versions', () =>
        HttpResponse.json(
          {
            version_id: 'v5',
            workflow_id: 'w1',
            version: 5,
            created_at: '2026-04-05T00:00:00Z',
          },
          { status: 201 },
        ),
      ),
    );
    const r = await createVersion('w1', { inputs_schema: {}, steps: [] });
    expect(r.version).toBe(5);
  });

  test('non-ok non-404/422 throws generic Error', async () => {
    server.use(
      http.get('*/api/v4/workflows/w1', () =>
        new HttpResponse(null, { status: 500 }),
      ),
    );
    await expect(getWorkflow('w1')).rejects.toThrow(/500/);
  });
});
