// Zepay demo — continuous checkout traffic against api-gateway.
//
// Storyboard §6:
//   - Continuous 50 RPS during the demo (default).
//   - /demo/spike bumps to 500 RPS for 60s on operator demand.
//   - Pool of ~500 seeded customers rotating through POST /checkout.
//   - 15% of calls include a concurrent /topup (demo-controller-issued,
//     not from k6) that seeds the balance-check window the retry's
//     second debit uses.
//
// Env vars:
//   GATEWAY_URL  default: http://api-gateway.payments-prod.svc.cluster.local:8080
//   RPS          default: 50
//   DURATION     default: 24h  (leave running; demo-controller restarts
//                              this job when it wants to change RPS)
import http from 'k6/http';
import { check, sleep } from 'k6';

const GATEWAY = __ENV.GATEWAY_URL || 'http://api-gateway.payments-prod.svc.cluster.local:8080';
const RPS     = parseInt(__ENV.RPS || '50', 10);

export const options = {
  scenarios: {
    checkouts: {
      executor: 'constant-arrival-rate',
      rate: RPS,
      timeUnit: '1s',
      duration: __ENV.DURATION || '24h',
      preAllocatedVUs: Math.max(50, RPS * 2),
      maxVUs:          Math.max(100, RPS * 10),
    },
  },
  // Demo: tolerate the 15s retry window so k6 doesn't mark those
  // requests as timeouts (they eventually return 200 via the retry).
  noConnectionReuse: false,
  insecureSkipTLSVerify: true,
};

// 500-customer pool keyed by index; rotates per request.
function pickCustomerId() {
  const idx = Math.floor(Math.random() * 500) + 1;
  return 'C-POOL-' + idx.toString().padStart(4, '0');
}

function pickAmountCents() {
  // Log-normal-ish distribution biased to small txns with a long tail.
  const r = Math.random();
  if (r < 0.6) return Math.floor(Math.random() * 3000) + 500;    // $5 - $35
  if (r < 0.9) return Math.floor(Math.random() * 8000) + 3000;   // $30 - $110
  return Math.floor(Math.random() * 40000) + 10000;              // $100 - $500
}

export default function () {
  const body = JSON.stringify({
    customer_id:   pickCustomerId(),
    cart_id:       'cart-' + Math.random().toString(36).slice(2, 10),
    amount_cents:  pickAmountCents(),
    currency:      'USD',
  });

  // Intentionally omitting Idempotency-Key — matches the real Zepay
  // pre-fix behavior (Bug #1). When the fix PRs land and k6 is
  // restarted with POST_FIX=true, we add the header to prove the
  // retry is safe.
  const headers = { 'Content-Type': 'application/json' };
  if (__ENV.POST_FIX === 'true') {
    headers['Idempotency-Key'] = 'k6-' + Math.random().toString(36).slice(2);
  }

  const res = http.post(`${GATEWAY}/api/v1/checkout`, body, {
    headers,
    // Allow the 15s fault + retry window.
    timeout: '45s',
  });
  check(res, { 'status was 200-2xx or 504': (r) => r.status < 600 });
  sleep(0);
}
