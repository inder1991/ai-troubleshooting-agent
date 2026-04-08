# Demo Scenario Tab — Design

**Goal:** Add a 3rd "Demo Scenario" tab to the How It Works page showing an e-commerce checkout failure scenario running inside an OpenShift cluster. Purely visual — no navigation, designed as a CXO demo presentation.

**Context:** The How It Works page currently has 2 tabs (Cluster Diagnostics, App Diagnostics) with animated workflow flowcharts. A similar scenario exists on the Home page (`Home/HowItWorks/ScenarioTab.tsx`) but uses different styling. This tab reuses the same scenario data but restyled with the warm amber palette and wrapped in an OpenShift cluster visual boundary.

---

## 1. Tab Bar

Add a 3rd tab to the existing tab bar in `HowItWorksView.tsx`:

| Tab | Label | Icon |
|-----|-------|------|
| 1 | Cluster Diagnostics | `deployed_code` |
| 2 | App Diagnostics | `bug_report` |
| **3** | **Demo Scenario** | **`play_lesson`** |

---

## 2. Layout (top to bottom)

### SEV-1 Banner

- Red left border (`#ef4444`), warm background gradient from red/10% to `WF_COLORS.pageBg`
- Title: "E-Commerce Checkout Failures & Slowness" — DM Sans bold, white
- Description: users reporting failed checkouts, 88.9% error rate, 10.3s latency
- SEV-1 badge: red background, uppercase

### OpenShift Cluster Container

A visual boundary box wrapping the entire microservice topology:

- **Header bar:** OpenShift-style icon + "OpenShift Cluster" label + namespace badge (`ecommerce-prod`)
- **Border:** `WF_COLORS.border` (`#3d3528`), 1px solid, rounded
- **Background:** slightly lighter than page — `WF_COLORS.cardBg` (`#252118`) at ~50% opacity
- **Contains:** the full service topology diagram

### Microservice Topology (inside cluster box)

Same data as existing `ScenarioTab.tsx`:

**Patient Zero (red, pulsing):**
- `checkout-frontend` — req/s: <0.01, latency: 10.3s, error: 88.9%

**Degraded (orange):**
- `checkout-service` — req/s: 0.07, latency: 7.18s, error: 1.23%

**Downstream (green, healthy):**
- `notification-service` — req/s: 0.07, latency: 1.19s, error: 0.11%
- `payment-service` — req/s: 0.07, latency: 208ms, error: 0.21%
- `user-service` — req/s: 0.07, latency: 428ms, error: 0%
- `inventory-service` — req/s: 0.07, latency: 1.23s, error: 0%

Layout: horizontal flow — patient zero → connector → degraded → fan-out SVG → 4 downstream stacked vertically.

Service node cards styled with:
- Background: `WF_COLORS.cardBg` (`#252118`)
- Border: service status color (red/orange/green)
- Font: DM Sans, Inter
- Metrics: colored by status (red/orange/green)

### Context Cards

3-column grid below the topology:

| Card | Top Border | Icon | Content |
|------|-----------|------|---------|
| Symptoms | `#e09f3e` (amber) | `troubleshoot` | checkout-frontend returning 5xx, page loads timing out 10+ seconds |
| Impact | `#ef4444` (red) | `warning` | 88.9% checkout attempts failing, ~$12K/min revenue loss, SLA breach imminent |
| Initial Hypothesis | `#10b981` (green) | `psychology` | Issue isolated to checkout-frontend → checkout-service path, likely cause in checkout-service or DB layer |

Card styling: `WF_COLORS.cardBg` background, `WF_COLORS.border` border, DM Sans headings.

**No CTA button.** The tab ends after the context cards.

---

## 3. Styling

All colors from `WF_COLORS`:
- Page background: `#1a1814`
- Card background: `#252118`
- Borders: `#3d3528`
- Text: `#e2e8f0` (primary), `#8a7e6b` (muted)
- Fonts: DM Sans (headings), Inter (body)
- Patient zero pulse: existing `animate-pulse-red` CSS animation

---

## 4. Components

| Component | Action |
|-----------|--------|
| `DemoScenarioTab.tsx` | **NEW** — restyled scenario with OpenShift cluster wrapper |
| `HowItWorksView.tsx` | **MODIFY** — add 3rd tab to tab bar and render `DemoScenarioTab` |

## What Does NOT Change

- No navigation to other tabs or views from this tab
- No backend changes
- No new dependencies
- Existing `Home/HowItWorks/ScenarioTab.tsx` stays untouched
- No changes to animation engine, configs, or other components
