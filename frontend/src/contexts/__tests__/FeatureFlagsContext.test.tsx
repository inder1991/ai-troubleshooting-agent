import { afterAll, afterEach, beforeAll, describe, expect, test } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import {
  FeatureFlagsProvider,
  useFeatureFlags,
} from '../FeatureFlagsContext';

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function Probe() {
  const { workflows, loading } = useFeatureFlags();
  if (loading) return <div>loading</div>;
  return <div>workflows: {workflows ? 'on' : 'off'}</div>;
}

function RetryProbe() {
  const { workflows, loading, retry } = useFeatureFlags();
  return (
    <div>
      <div data-testid="state">
        {loading ? 'loading' : `workflows: ${workflows ? 'on' : 'off'}`}
      </div>
      <button onClick={() => retry()}>retry</button>
    </div>
  );
}

describe('FeatureFlagsContext', () => {
  test('probe 200 -> workflows enabled', async () => {
    server.use(
      http.get('*/api/v4/workflows', () =>
        HttpResponse.json({ workflows: [] }),
      ),
    );
    render(
      <FeatureFlagsProvider>
        <Probe />
      </FeatureFlagsProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText(/workflows: on/i)).toBeInTheDocument(),
    );
  });

  test('probe 404 -> workflows disabled', async () => {
    server.use(
      http.get(
        '*/api/v4/workflows',
        () => new HttpResponse(null, { status: 404 }),
      ),
    );
    render(
      <FeatureFlagsProvider>
        <Probe />
      </FeatureFlagsProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText(/workflows: off/i)).toBeInTheDocument(),
    );
  });

  test('retry() re-probes and flips state', async () => {
    // First: 404 (off). After retry: 200 (on).
    let hits = 0;
    server.use(
      http.get('*/api/v4/workflows', () => {
        hits += 1;
        if (hits === 1) return new HttpResponse(null, { status: 404 });
        return HttpResponse.json({ workflows: [] });
      }),
    );

    render(
      <FeatureFlagsProvider>
        <RetryProbe />
      </FeatureFlagsProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId('state')).toHaveTextContent('workflows: off'),
    );

    await act(async () => {
      screen.getByText('retry').click();
    });

    await waitFor(() =>
      expect(screen.getByTestId('state')).toHaveTextContent('workflows: on'),
    );
    expect(hits).toBe(2);
  });

  test('network failure treated as disabled', async () => {
    server.use(
      http.get('*/api/v4/workflows', () => {
        return HttpResponse.error();
      }),
    );
    render(
      <FeatureFlagsProvider>
        <Probe />
      </FeatureFlagsProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText(/workflows: off/i)).toBeInTheDocument(),
    );
  });
});
