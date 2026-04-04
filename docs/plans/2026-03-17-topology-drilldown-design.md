# Two-Level Drill-Down Topology — Design Document

**Goal:** Replace the single-canvas 35-device topology (which produces unreadable edge spaghetti) with a two-level drill-down: Level 1 shows 5 environment cards connected by WAN links, Level 2 shows devices within one environment arranged in clean tiers.

**Architecture:** Parent component manages level state. Level 1 = `TopologyOverview.tsx` (5 cards + WAN edges). Level 2 = `TopologyDetail.tsx` (devices in tiers + intra-group edges + navigation badges). New backend endpoint `/api/v5/topology/overview` for Level 1 summary. Existing V5 endpoint filtered by group for Level 2.

---

## Level 1: Environment Overview

5 large cards on a clean canvas. Cards connected by labeled WAN links.

Each card shows:
- Environment name + icon + accent color
- Device count
- Health summary (worst status + counts)

WAN links between cards show:
- Connection type (MPLS, DirectConnect, ExpressRoute, FastConnect)
- Status (up/down)

Click a card → transitions to Level 2.

## Level 2: Environment Detail

Devices within one environment only. Arranged in tiers top-to-bottom:
- Tier labels as horizontal dividers (PERIMETER, CORE, DISTRIBUTION, ACCESS)
- HA pairs shown side by side with dashed HA line
- Only intra-group edges rendered (short, clean, no spaghetti)

Cross-group connections shown as:
- Navigation badges on devices (colored pills: [AWS] [Azure] [OCI])
- Click badge → navigate to that environment's detail
- WAN connections panel at bottom with text list of exit paths

## Navigation

- Overview → Detail: click card, slide transition
- Detail → Detail: click navigation badge on device
- Detail → Overview: back button or Escape
- URL routing: /topology, /topology/onprem, /topology/aws

## Backend

- `GET /api/v5/topology/overview` — environment summaries + WAN connections
- `GET /api/v5/topology?group=onprem` — filtered V5 data for one group

## Components

- `TopologyOverview.tsx` — Level 1 (new)
- `TopologyDetail.tsx` — Level 2 (new)
- `LiveTopologyViewV2.tsx` — parent managing level state (modified)
- `LiveDeviceNode.tsx` — device cards (existing, unchanged)
- Backend: overview endpoint + group filter on existing V5 endpoint
