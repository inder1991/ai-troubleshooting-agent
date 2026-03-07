# Enterprise Manual Test Strategy — Network Module

**Purpose:** Step-by-step manual testing playbook for an SDET to validate all network features as an enterprise user would use them in a hybrid on-prem + cloud environment.

**Prerequisites:**
- Backend running: `cd backend && uvicorn src.api.main:app --reload --port 8000`
- Frontend running: `cd frontend && npm run dev`
- Browser open at `http://localhost:5173`

---

## Phase 1: Topology Setup — Build Enterprise Network from Scratch

**Goal:** Build a realistic hybrid enterprise topology through the UI to validate the topology editor works end-to-end.

**Enterprise Scenario:** You are a network engineer setting up monitoring for a 2-DC enterprise with a cloud extension.

### Test 1.1: Navigate to Topology Editor

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Infrastructure → Topology** in sidebar | Topology Editor loads with empty canvas, dot grid background |
| 2 | Verify toolbar buttons | Save, Load, Refresh from KG, Import IPAM, Adapter Status, Undo, Redo, Delete, Promote visible |
| 3 | Verify Node Palette (left sidebar) | Categories visible: Text Annotation + device types + container types (VPC, Subnet, HA Group, etc.) |
| 4 | Verify Property Panel (right sidebar) | Empty or shows "Select a node to edit properties" |

### Test 1.2: Create VPC Container

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **VPC** from palette onto canvas | VPC container node appears with default label |
| 2 | Click the VPC node | Property Panel shows: Name, CIDR, Cloud Provider, Region |
| 3 | Set Name: `Enterprise-VPC-East` | Label updates on canvas |
| 4 | Set CIDR: `10.0.0.0/16` | CIDR shown on node |
| 5 | Set Cloud Provider: `AWS` | Provider badge visible |
| 6 | Set Region: `us-east-1` | Region shown in panel |

### Test 1.3: Create Subnets Inside VPC

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **Subnet** into the VPC container | Subnet snaps inside VPC bounds |
| 2 | Set Name: `DMZ-Subnet`, CIDR: `10.0.1.0/24` | Subnet labeled on canvas |
| 3 | Drag another **Subnet** into VPC | Second subnet appears inside VPC |
| 4 | Set Name: `Inside-Subnet`, CIDR: `10.0.2.0/24` | Subnet labeled |
| 5 | Drag a third **Subnet** into VPC | Third subnet appears |
| 6 | Set Name: `Mgmt-Subnet`, CIDR: `10.0.3.0/24` | Subnet labeled |

### Test 1.4: Add Firewall Device

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **firewall** device into DMZ-Subnet | Firewall node appears with hexagonal shape inside subnet |
| 2 | Click the firewall node | Property Panel shows: Name, IP, Vendor, Type, Zone + firewall-specific buttons |
| 3 | Set Name: `FW-Core-01` | Name updates on canvas |
| 4 | Set IP: `10.0.1.1` | IP shown |
| 5 | Set Vendor: `Palo Alto` | Vendor shown |
| 6 | Verify "Manage Adapters" button visible | Button present (firewall-specific) |
| 7 | Verify "Add Interface (ENI)" button visible | Button present (firewall-specific) |

### Test 1.5: Add Interfaces to Firewall

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **"+ Add Interface (ENI)"** | Interface node appears near firewall, connected by edge, positioned at TOP |
| 2 | Click the interface node | Panel shows: Name, IP, Role, Parent Device |
| 3 | Set Name: `eth0`, IP: `10.0.1.2`, Role: `outside (untrust)` | Interface updated |
| 4 | Click firewall again, click **"+ Add Interface (ENI)"** again | 2nd interface appears at RIGHT of firewall |
| 5 | Set Name: `eth1`, IP: `10.0.2.2`, Role: `inside (trust)` | Interface updated |
| 6 | Click firewall, add 3rd interface | 3rd interface at BOTTOM |
| 7 | Set Name: `eth2`, IP: `10.0.3.2`, Role: `management` | Interface updated |
| 8 | Click firewall, add 4th interface | 4th interface at LEFT |
| 9 | Set Name: `eth3`, IP: `10.0.1.3`, Role: `dmz` | Interface updated |
| 10 | Verify all 4 interfaces radiate to different sides | No interfaces stacked on same side |

### Test 1.6: Add Router and Switch

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **router** device onto canvas (outside VPC) | Router node appears |
| 2 | Set Name: `RTR-Edge-01`, IP: `10.0.0.1`, Vendor: `Cisco` | Router configured |
| 3 | Drag **switch** device into Inside-Subnet | Switch node inside subnet |
| 4 | Set Name: `SW-Access-01`, IP: `10.0.2.10`, Vendor: `Cisco` | Switch configured |

### Test 1.7: Create Connections (Edges)

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag from router's bottom handle to firewall's top handle | Edge created with label "connected_to" |
| 2 | Drag from firewall's bottom handle to switch's top handle | Second edge created |
| 3 | Hover over an edge | Edge stroke thickens, glow appears |
| 4 | Click an edge | Edge highlights cyan, Property Panel shows edge type dropdown |
| 5 | Change edge type to `routes_to` | Edge label updates to "routes_to" |

### Test 1.8: Add HA Group

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **HA Group** container onto canvas | HA Group container appears |
| 2 | Set Name: `FW-HA-Pair` | Label updates |
| 3 | Set HA Mode: `Active/Passive` | Mode shown |
| 4 | Set Virtual IPs: `10.0.1.100, 10.0.2.100` | VIPs shown |
| 5 | Drag FW-Core-01 INTO the HA Group | Firewall nests inside HA group |
| 6 | Add another firewall `FW-Core-02` inside HA Group | Second FW in same group |

### Test 1.9: Add Text Annotations

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **Text Annotation** from palette onto canvas | Text block appears |
| 2 | Click it, set Text: `US-East Production DC` | Text visible on canvas |
| 3 | Set Font Size: `18px`, Color: cyan | Text styled |
| 4 | Resize the annotation by dragging corner | Text block resizes |
| 5 | Connect text annotation to VPC via handle | Leader line drawn |

### Test 1.10: Save and Load Topology

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Save** button | Toast shows "Topology saved successfully" |
| 2 | Refresh the browser page | Canvas empty |
| 3 | Click **Load** button | Previous topology restored with all nodes, edges, positions |
| 4 | Verify all nodes, connections, annotations intact | Everything matches pre-save state |

### Test 1.11: Undo / Redo

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Delete a node (select + press Delete key) | Node removed |
| 2 | Click **Undo** (or Ctrl+Z) | Node restored |
| 3 | Click **Redo** (or Ctrl+Shift+Z) | Node removed again |

### Test 1.12: Delete Nodes and Edges

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click an edge, click **"Delete Edge"** in panel | Edge removed, nodes remain |
| 2 | Select a device node, click **Delete** toolbar button | Device removed, its edges removed |
| 3 | Select a container with children, delete | Container and children removed |

---

## Phase 2: IPAM Import — Bulk Data Ingestion

**Goal:** Import real-world network inventory via CSV, verify auto-population of topology.

**Enterprise Scenario:** Your organization maintains an IPAM spreadsheet. Import it to bootstrap the topology.

### Test 2.1: Download Sample CSV

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Navigate to **Infrastructure → IPAM** | IPAM Inventory page loads |
| 2 | Verify empty state message | "No devices imported yet. Click 'Import IPAM' to get started." |
| 3 | Click **"Import IPAM"** button | Upload dialog opens |
| 4 | Click **"Download Sample CSV"** | CSV file downloads with sample data |
| 5 | Open downloaded CSV | Contains columns: ip, subnet, device, zone, vlan, description, device_type |

### Test 2.2: Prepare Enterprise IPAM Data

Create a CSV file `enterprise-ipam.csv` with this content:

```csv
ip,subnet,device,zone,vlan,description,device_type
10.0.1.1,10.0.1.0/24,fw-core-01,dmz,100,Core perimeter firewall,firewall
10.0.1.2,10.0.1.0/24,fw-core-02,dmz,100,Core perimeter firewall standby,firewall
10.0.2.1,10.0.2.0/24,rtr-edge-01,outside,200,Edge router to ISP,router
10.0.2.2,10.0.2.0/24,rtr-edge-02,outside,200,Edge router backup,router
10.0.3.1,10.0.3.0/24,sw-access-01,inside,300,Access layer switch,switch
10.0.3.2,10.0.3.0/24,sw-access-02,inside,300,Access layer switch 2,switch
10.0.4.1,10.0.4.0/24,app-server-01,inside,400,Application server,host
10.0.4.2,10.0.4.0/24,db-server-01,inside,400,Database server,host
10.0.5.1,10.0.5.0/24,lb-prod-01,dmz,500,Production load balancer,load_balancer
172.16.0.1,172.16.0.0/24,vpn-gw-01,outside,600,VPN gateway to cloud,cloud_gateway
```

### Test 2.3: Import IPAM CSV

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **"Import IPAM"** on IPAM page | Upload dialog opens |
| 2 | Drag `enterprise-ipam.csv` into drop zone | File accepted, upload starts |
| 3 | Wait for progress bar to complete | Shows "10 devices imported, 5 subnets imported" |
| 4 | Click **"Close & View"** | Dialog closes |
| 5 | Verify Devices tab shows 10 devices | All devices listed with correct Name, IP, Type, Zone, VLAN |
| 6 | Verify Subnets tab shows 5 subnets | CIDRs: 10.0.1.0/24 through 10.0.5.0/24 and 172.16.0.0/24 |
| 7 | Summary cards show: Total Devices = 10, Total Subnets = 5+ | Counts match |

### Test 2.4: Search and Filter IPAM Data

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Type `firewall` in search box | Only fw-core-01 and fw-core-02 shown |
| 2 | Clear search, type `10.0.3` | Shows sw-access-01, sw-access-02 |
| 3 | Switch to Subnets tab | Subnet list displayed |
| 4 | Type `10.0.4` in search | Only 10.0.4.0/24 shown |

### Test 2.5: IPAM to Topology Integration

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Navigate to **Infrastructure → Topology** | Topology Editor opens |
| 2 | Click **"Import IPAM"** in toolbar | Upload dialog opens |
| 3 | Import the same CSV | Devices appear on canvas as nodes |
| 4 | Verify devices are positioned on canvas | All 10 devices visible |
| 5 | Click **"Refresh from KG"** | Canvas refreshes with knowledge graph data |

### Test 2.6: Invalid IPAM Data

Create `bad-ipam.csv`:
```csv
ip,subnet,device,zone,vlan,description,device_type
999.999.999.999,10.0.1.0/24,bad-device,dmz,100,Invalid IP,firewall
10.0.1.1,not-a-cidr,bad-subnet,dmz,100,Invalid CIDR,router
,10.0.1.0/24,no-ip-device,dmz,100,Missing IP,switch
```

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Import `bad-ipam.csv` | Upload completes with warnings |
| 2 | Verify warnings list shows validation errors | Invalid IP, invalid CIDR flagged |
| 3 | Valid rows (if any) are imported | Partial import succeeds |

---

## Phase 3: Adapter Integration — Configure Firewall Adapters

**Goal:** Configure adapter instances for enterprise firewalls and verify connectivity.

**Enterprise Scenario:** Connect DebugDuck to your Palo Alto Panorama and AWS Security Groups.

### Test 3.1: Navigate to Adapters Page

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Infrastructure → Adapters** | Network Adapters page loads |
| 2 | Verify empty state | "No adapters configured yet. Click 'Add Adapter' to get started." |
| 3 | Summary cards show: Total=0, Connected=0, Issues=0 | All zero |

### Test 3.2: Add Palo Alto Panorama Adapter

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **"Add Adapter"** | Adapter form dialog opens |
| 2 | Set Instance Label: `US-East Panorama` | Label entered |
| 3 | Set Vendor: `Palo Alto` | Vendor selected, Palo Alto-specific fields appear |
| 4 | Verify Mode toggle: "Panorama" / "Standalone" | Toggle visible, Panorama selected by default |
| 5 | Set API Endpoint: `https://panorama.example.com` | Endpoint entered |
| 6 | Set API Key: `test-api-key-12345` | Key entered (masked) |
| 7 | Click **"Test Connection"** | Connection test runs — shows result (success/fail) |
| 8 | If Panorama mode: verify "Discover Device Groups" button | Button visible |
| 9 | Click **"Create"** | Dialog closes, adapter appears in table |
| 10 | Verify table row: Label=`US-East Panorama`, Vendor=`Palo Alto`, Status badge shown | Row displayed correctly |

### Test 3.3: Add AWS Security Group Adapter

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **"Add Adapter"** | Form opens |
| 2 | Set Label: `AWS-Prod-SG` | Label entered |
| 3 | Set Vendor: `AWS Security Group` | AWS-specific fields appear: Region, SG ID, Access Key, Secret Key |
| 4 | Set Region: `us-east-1` | Region entered |
| 5 | Set Security Group ID: `sg-0123456789abcdef0` | SG ID entered |
| 6 | Set Access Key: `AKIA...` (test value) | Key entered |
| 7 | Set Secret Key: `test-secret` | Key entered (masked) |
| 8 | Click **"Create"** | Adapter created, shows in table |

### Test 3.4: Edit Adapter

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Edit** (pencil icon) on US-East Panorama row | Edit form opens with pre-filled fields |
| 2 | Verify Vendor dropdown is disabled | Cannot change vendor after creation |
| 3 | Verify API Key shows "(leave blank to keep current)" | Hint text visible |
| 4 | Change Label to `US-East Panorama v2` | Label updated |
| 5 | Click **"Update"** | Table reflects new label |

### Test 3.5: Refresh and Delete Adapter

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Refresh** (icon) on an adapter row | Status refreshes (may change to Connected/Unreachable) |
| 2 | Click **Delete** (icon) on AWS-Prod-SG row | Confirmation prompt appears |
| 3 | Confirm deletion | Adapter removed from table |
| 4 | Summary cards update: Total decremented | Count accurate |

### Test 3.6: Adapter Config from Topology Editor

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Go to Topology Editor, select a firewall node | Firewall properties shown |
| 2 | Click **"Manage Adapters"** | Adapter Config dialog opens with Vendor, Endpoint, API Key, Extra Config |
| 3 | Set Vendor: `Palo Alto`, Endpoint: `https://fw.local`, Key: `test` | Fields filled |
| 4 | Click **"Test Connection"** | Connection test result displayed |
| 5 | Click **Save** | Dialog closes, adapter configured for this device |

### Test 3.7: Search Adapters

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Type `Panorama` in search box on Adapters page | Only Panorama adapter shown |
| 2 | Type `nonexistent` | No results shown |
| 3 | Clear search | All adapters shown |

---

## Phase 4: Network Diagnosis — Run Flow Analysis

**Goal:** Execute network path diagnoses and verify the full pipeline produces correct results.

**Enterprise Scenario:** A user reports they can't reach the web application. Diagnose the network path.

### Test 4.1: Navigate to Network Path Diagnosis

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Diagnostics → Network Path** | Network troubleshooting form loads |
| 2 | Verify form fields: Source IP, Destination IP, Port, Protocol | All fields present |
| 3 | Verify Protocol toggle: TCP / UDP | Toggle works, TCP selected by default |

### Test 4.2: Valid Diagnosis — Happy Path

**Precondition:** Topology with at least 2 devices and routes exists (from Phase 1 or 2).

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Set Source IP: `10.0.2.1` (router) | Valid IP, no error |
| 2 | Set Destination IP: `10.0.4.1` (app server) | Valid IP, no error |
| 3 | Set Port: `443` | Valid port |
| 4 | Set Protocol: `TCP` | TCP selected |
| 5 | Click **"Deploy Mission"** | Network War Room opens |
| 6 | Verify header shows: "Network War Room", phase badge | Header visible |
| 7 | Wait for diagnosis to complete | Phase badge turns green ("complete" or "done") |
| 8 | **DiagnosisPanel** (left): Executive Summary present | Summary describes path analysis result |
| 9 | Confidence Meter shows percentage | Value between 0-100% with breakdown |
| 10 | Path Hop List shows traversed devices | Hop-by-hop path visible |
| 11 | **NetworkCanvas** (center): Topology visualization | Devices and path highlighted |
| 12 | **NetworkEvidenceStack** (right): Evidence findings | At least 1 evidence item |

### Test 4.3: Diagnosis — Blocked Path

**Precondition:** Firewall has deny rule for the tested flow.

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Diagnose a flow that hits a deny rule | War Room opens |
| 2 | Wait for completion | Phase complete |
| 3 | Executive Summary mentions "BLOCKED" or "DENIED" | Blocked verdict shown |
| 4 | Firewall verdict card shows DENY | Red/blocked indicator |
| 5 | Next Steps suggest reviewing firewall rules | Actionable recommendations |

### Test 4.4: Diagnosis — Unknown IPs (No Topology Match)

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Set Source IP: `192.168.99.1` (not in topology) | Valid IP format |
| 2 | Set Destination IP: `192.168.99.2` | Valid IP format |
| 3 | Set Port: `80` | Valid |
| 4 | Click **"Deploy Mission"** | War Room opens |
| 5 | Diagnosis shows "no_path_known" or "failed" status | No topology data for these IPs |
| 6 | Warning banner: "Import IPAM data or build a topology canvas" | Guidance shown |

### Test 4.5: Diagnosis — Input Validation

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Set Source IP: `999.999.999.999` | Red border, error message: invalid IP |
| 2 | Set Source IP: `abc` | Red border, validation error |
| 3 | Set Port: `99999` | Error: port must be 1-65535 |
| 4 | Set Port: `0` | Error: port must be 1-65535 |
| 5 | Leave Source IP empty, click Deploy | Validation prevents submission |

### Test 4.6: Bidirectional Diagnosis

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Run a diagnosis (any valid flow) | War Room opens |
| 2 | After completion, look for **A→B / B→A toggle** buttons in header | Toggle buttons visible |
| 3 | Click **B→A** button | View switches to return path analysis |
| 4 | Verify return path has its own verdict and hops | Different or same path shown |
| 5 | Toggle back to **A→B** | Original forward path shown |

### Test 4.7: NAT Translation Visibility

**Precondition:** Topology has NAT rules (SNAT/DNAT configured).

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Diagnose a flow that traverses a NAT device | War Room opens |
| 2 | Wait for completion | Phase complete |
| 3 | NAT Identity Chain section visible in DiagnosisPanel | Shows original → translated IP mapping |
| 4 | Each NAT hop shows: device, direction (SNAT/DNAT), original/translated | Chain visible |

### Test 4.8: Concurrent / Repeat Diagnosis

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Run diagnosis with same src/dst/port as Test 4.2 | War Room opens |
| 2 | Note the Flow ID and Session ID | IDs displayed in session info |
| 3 | Go back, run the exact same flow within 60 seconds | Should return cached result (same flow_id) |
| 4 | Wait 60+ seconds, run again | New flow_id created (cache expired) |

---

## Phase 5: HA & Failover Scenarios

**Goal:** Verify High Availability group configuration and behavior.

**Enterprise Scenario:** Your core firewalls are in Active/Passive HA. Verify the topology models this correctly.

### Test 5.1: Create HA Group in Topology

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Open Topology Editor | Editor loads |
| 2 | Drag **HA Group** container onto canvas | HA Group node appears |
| 3 | Set Name: `Core-FW-HA` | Named |
| 4 | Set HA Mode: `Active/Passive` | Mode configured |
| 5 | Set Virtual IPs: `10.0.1.100` | VIP configured |
| 6 | Drag two firewall devices INTO the HA Group | Both firewalls nested inside HA container |
| 7 | Set FW1 Name: `FW-Active`, FW2 Name: `FW-Standby` | Both named |
| 8 | Save topology | Saved successfully |

### Test 5.2: Verify HA in Knowledge Graph

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **"Promote to Infrastructure"** | Toast: "Promoted to infrastructure" |
| 2 | Run a diagnosis that traverses the HA pair | Diagnosis routes through active member |
| 3 | Path should show the active firewall, not standby | Hop list includes FW-Active |

---

## Phase 6: Cloud Hybrid Topology

**Goal:** Build and test cloud components — VPCs, VPN tunnels, transit gateways, NACLs, load balancers.

**Enterprise Scenario:** Your enterprise extends to AWS with a VPN tunnel connecting on-prem DC to a cloud VPC.

### Test 6.1: Add Cloud VPC

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | In Topology Editor, drag **VPC** onto canvas | VPC container appears |
| 2 | Set Name: `AWS-Prod-VPC` | Named |
| 3 | Set CIDR: `10.1.0.0/16` | CIDR set |
| 4 | Set Cloud Provider: `AWS` | Provider badge visible |
| 5 | Set Region: `us-east-1` | Region set |

### Test 6.2: Add Availability Zone and Subnets

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **Availability Zone** INTO VPC | AZ container nested in VPC |
| 2 | Set Zone Name: `us-east-1a` | Named |
| 3 | Drag **Subnet** into AZ | Subnet nested in AZ, which is in VPC |
| 4 | Set Subnet Name: `Public-Subnet`, CIDR: `10.1.0.0/24` | Configured |
| 5 | Add another Subnet: `Private-Subnet`, CIDR: `10.1.1.0/24` | Second subnet |
| 6 | Verify 3-level nesting: VPC > AZ > Subnet | Visual hierarchy correct |

### Test 6.3: Add Load Balancer

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **load_balancer** device type into Public-Subnet | LB node inside subnet |
| 2 | Select it, verify Type shows `load_balancer` | LB-specific fields appear |
| 3 | Set Name: `ALB-Prod` | Named |
| 4 | Set LB Type: `ALB` | Type set |
| 5 | Set Scheme: `Internet Facing` | Scheme set |
| 6 | Add host devices in Private-Subnet as targets | Target devices placed |
| 7 | Draw edge from LB to each target: type `load_balances` | Load balancing edges created |

### Test 6.4: Add VPN Tunnel

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **vpn_tunnel** device type onto canvas | VPN node appears |
| 2 | Select it, verify VPN-specific fields appear | Tunnel Type, Encryption, Remote Gateway |
| 3 | Set Name: `Site-to-AWS-VPN` | Named |
| 4 | Set Tunnel Type: `IPSec` | Type set |
| 5 | Set Encryption: `AES-256-GCM` | Encryption set |
| 6 | Set Remote Gateway: `52.10.20.30` | Remote IP set |
| 7 | Draw edges: on-prem router → VPN → cloud gateway | Tunnel path connected |
| 8 | Set edge types to `tunnel_to` | Edge labels update |

### Test 6.5: Add Transit Gateway

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **transit_gateway** device type | TGW node appears |
| 2 | Set Name: `TGW-Central` | Named |
| 3 | Draw edge from TGW to VPC: type `attached_to` | Attachment edge created |
| 4 | Draw edge from TGW to VPN: type `tunnel_to` | VPN attachment |

### Test 6.6: Add Compliance Zone

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Drag **Compliance Zone** container | Zone container appears |
| 2 | Set Name: `PCI-Zone` | Named |
| 3 | Set Compliance Framework: `PCI-DSS` | Framework set |
| 4 | Set Zone Type: `Data` | Type set |
| 5 | Drag payment-related devices INTO compliance zone | Devices nested correctly |

### Test 6.7: Full Hybrid Path Diagnosis

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Save and Promote topology | Infrastructure updated |
| 2 | Diagnose: Source=`10.0.2.1` (on-prem) → Dest=`10.1.1.10` (cloud private) | War Room opens |
| 3 | Wait for completion | Diagnosis complete |
| 4 | Verify path crosses: on-prem router → VPN → TGW → VPC → subnet → target | Multi-hop path shown |
| 5 | Check for VPN segment mention in evidence | VPN crossing noted |
| 6 | Check vpc_boundary_crossings in results | VPC crossing detected |

---

## Phase 7: Monitoring & Drift Detection

**Goal:** Verify the Observatory dashboard shows live network state and detects configuration drift.

**Enterprise Scenario:** Monitor your production network for unauthorized changes and discover unknown devices.

### Test 7.1: Navigate to Observatory

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Infrastructure → Observatory** | Observatory page loads |
| 2 | Verify 4 tabs: Live Topology, Device Health, Traffic Flows, Alerts | All tabs present |
| 3 | Verify Golden Signals ribbon: Avg Latency, Packet Loss, Link Utilization, Active Alerts | 4 metric cards with sparklines |
| 4 | Verify status badges in header: "X/Y UP", "Drift", "Discovered" | Status indicators visible |
| 5 | Verify "Updated Xs ago" counter | Live update counter present |

### Test 7.2: Device Health Tab (NOC Wall)

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Device Health** tab | Device status cards displayed |
| 2 | Each device card shows: name, status, key metrics | Cards rendered |
| 3 | Verify color coding: green=healthy, amber=warning, red=critical | Status colors accurate |
| 4 | Click a device card | Switches to topology view focused on that device (or shows detail) |

### Test 7.3: Live Topology Tab

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Live Topology** tab | Network topology visualization loads |
| 2 | Devices shown with status overlays | Green/amber/red status indicators on nodes |
| 3 | Drift events listed in sidebar | Any drift events displayed |
| 4 | Discovery candidates panel shows unknown IPs | Candidate list (if any) |

### Test 7.4: Traffic Flows Tab

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Traffic Flows** tab | Flow visualization loads |
| 2 | Links show utilization percentages | Traffic data on edges |

### Test 7.5: Alerts Tab

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Click **Alerts** tab | Alert list loads |
| 2 | Alerts severity-coded: red=critical, amber=warning, blue=info | Color coding correct |
| 3 | Click alert bell icon in header | Dropdown shows recent alerts |
| 4 | "View all alerts" link at bottom | Navigates to full alerts view |

### Test 7.6: Discovery Candidates

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | If discovery candidates exist, view the list | Shows IP, MAC, hostname, first/last seen |
| 2 | Promote a candidate to topology | Device added to topology as a known device |
| 3 | Dismiss a candidate | Candidate removed from list |

---

## Phase 8: Edge Cases & Negative Testing

**Goal:** Verify the system handles invalid inputs, missing data, and error conditions gracefully.

### Test 8.1: Topology Editor — Edge Cases

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Try to save an empty canvas | Either saves empty or shows info message |
| 2 | Try to create a connection from a handle to the same node | Connection rejected or ignored |
| 3 | Add 20+ devices, verify canvas performance | Canvas remains responsive |
| 4 | Deeply nest containers (VPC > AZ > Subnet > HA > Device) | All levels render correctly |
| 5 | Set a very long device name (100+ chars) | Name truncated or wraps, doesn't break layout |
| 6 | Set invalid IP (e.g., `300.0.0.1`) in property panel | Red border, validation error shown |
| 7 | Set invalid CIDR (e.g., `10.0.0.0/33`) in subnet | Validation error |

### Test 8.2: IPAM — Edge Cases

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Import an empty CSV (just headers) | No error, shows "0 devices imported" |
| 2 | Import a CSV with 1000+ rows | Import completes (may take time), all rows processed |
| 3 | Import the same CSV twice | Handles duplicates gracefully (skip or update) |
| 4 | Import a non-CSV file (e.g., .pdf) | Error message or file rejected |
| 5 | Import CSV with missing columns | Error or partial import with warnings |

### Test 8.3: Adapter — Edge Cases

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Create adapter with empty label | Validation prevents creation |
| 2 | Create adapter with unreachable endpoint | Created but status shows "Unreachable" |
| 3 | Create adapter with invalid API key | Created but status shows "Auth Failed" |
| 4 | Delete an adapter that's bound to devices | Adapter deleted, devices unbound |

### Test 8.4: Diagnosis — Edge Cases

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Diagnose with source == destination | Either error or trivial result |
| 2 | Diagnose with port 0 | Validation error |
| 3 | Diagnose when backend is down | Error message shown gracefully |
| 4 | Navigate away during in-progress diagnosis | Can return to war room and see results |

### Test 8.5: Navigation — Cross-Feature Flow

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Build topology → Import IPAM → Configure adapters → Run diagnosis | Full workflow end-to-end |
| 2 | From diagnosis results, navigate to topology to verify the path | Topology shows relevant devices |
| 3 | From Observatory, identify drift → go to topology to fix | Cross-page navigation works |
| 4 | Use browser back/forward buttons throughout | Navigation history works |
| 5 | Open multiple browser tabs on different pages | No cross-tab interference |

### Test 8.6: Reachability Matrix

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Navigate to **Infrastructure → Matrix** | Reachability Matrix page loads |
| 2 | Verify zone-to-zone reachability grid | Matrix displays zones as rows/columns |
| 3 | Each cell shows allow/deny/partial status | Color-coded cells |
| 4 | Click a cell for details | Details of rules/paths shown |

---

## Appendix A: Test Data Reference

### Enterprise Topology Summary

| Device | Type | IP | Zone | Subnet |
|--------|------|-----|------|--------|
| FW-Core-01 | Firewall | 10.0.1.1 | DMZ | 10.0.1.0/24 |
| FW-Core-02 | Firewall | 10.0.1.2 | DMZ | 10.0.1.0/24 |
| RTR-Edge-01 | Router | 10.0.2.1 | Outside | 10.0.2.0/24 |
| SW-Access-01 | Switch | 10.0.3.1 | Inside | 10.0.3.0/24 |
| App-Server-01 | Host | 10.0.4.1 | Inside | 10.0.4.0/24 |
| DB-Server-01 | Host | 10.0.4.2 | Inside | 10.0.4.0/24 |
| LB-Prod-01 | Load Balancer | 10.0.5.1 | DMZ | 10.0.5.0/24 |
| VPN-GW-01 | Cloud Gateway | 172.16.0.1 | Outside | 172.16.0.0/24 |

### Cloud Topology Summary

| Resource | Type | CIDR/IP | Region |
|----------|------|---------|--------|
| AWS-Prod-VPC | VPC | 10.1.0.0/16 | us-east-1 |
| Public-Subnet | Subnet | 10.1.0.0/24 | us-east-1a |
| Private-Subnet | Subnet | 10.1.1.0/24 | us-east-1a |
| ALB-Prod | Load Balancer | 10.1.0.10 | us-east-1 |
| TGW-Central | Transit GW | — | us-east-1 |
| Site-to-AWS-VPN | VPN Tunnel | IPSec | — |

### Key Diagnosis Flows to Test

| # | Source | Destination | Port | Expected Result |
|---|--------|-------------|------|----------------|
| 1 | 10.0.2.1 (router) | 10.0.4.1 (app server) | 443 | ALLOW — internal path |
| 2 | 10.0.2.1 (router) | 10.0.4.2 (db server) | 3306 | DENY — DB port blocked |
| 3 | 10.0.4.1 (on-prem) | 10.1.1.10 (cloud) | 443 | ALLOW — cross-VPN path |
| 4 | 192.168.99.1 | 192.168.99.2 | 80 | NO PATH — unknown IPs |
| 5 | 10.0.2.1 | 10.0.5.1 (LB VIP) | 443 | ALLOW — through LB |

---

## Appendix B: Pass/Fail Tracking Template

| Phase | Test ID | Test Name | Status | Notes |
|-------|---------|-----------|--------|-------|
| 1 | 1.1 | Navigate to Topology Editor | ⬜ | |
| 1 | 1.2 | Create VPC Container | ⬜ | |
| 1 | 1.3 | Create Subnets Inside VPC | ⬜ | |
| 1 | 1.4 | Add Firewall Device | ⬜ | |
| 1 | 1.5 | Add Interfaces to Firewall | ⬜ | |
| 1 | 1.6 | Add Router and Switch | ⬜ | |
| 1 | 1.7 | Create Connections (Edges) | ⬜ | |
| 1 | 1.8 | Add HA Group | ⬜ | |
| 1 | 1.9 | Add Text Annotations | ⬜ | |
| 1 | 1.10 | Save and Load Topology | ⬜ | |
| 1 | 1.11 | Undo / Redo | ⬜ | |
| 1 | 1.12 | Delete Nodes and Edges | ⬜ | |
| 2 | 2.1 | Download Sample CSV | ⬜ | |
| 2 | 2.2 | Prepare Enterprise IPAM Data | ⬜ | |
| 2 | 2.3 | Import IPAM CSV | ⬜ | |
| 2 | 2.4 | Search and Filter IPAM Data | ⬜ | |
| 2 | 2.5 | IPAM to Topology Integration | ⬜ | |
| 2 | 2.6 | Invalid IPAM Data | ⬜ | |
| 3 | 3.1 | Navigate to Adapters Page | ⬜ | |
| 3 | 3.2 | Add Palo Alto Panorama Adapter | ⬜ | |
| 3 | 3.3 | Add AWS Security Group Adapter | ⬜ | |
| 3 | 3.4 | Edit Adapter | ⬜ | |
| 3 | 3.5 | Refresh and Delete Adapter | ⬜ | |
| 3 | 3.6 | Adapter Config from Topology Editor | ⬜ | |
| 3 | 3.7 | Search Adapters | ⬜ | |
| 4 | 4.1 | Navigate to Network Path Diagnosis | ⬜ | |
| 4 | 4.2 | Valid Diagnosis — Happy Path | ⬜ | |
| 4 | 4.3 | Diagnosis — Blocked Path | ⬜ | |
| 4 | 4.4 | Diagnosis — Unknown IPs | ⬜ | |
| 4 | 4.5 | Diagnosis — Input Validation | ⬜ | |
| 4 | 4.6 | Bidirectional Diagnosis | ⬜ | |
| 4 | 4.7 | NAT Translation Visibility | ⬜ | |
| 4 | 4.8 | Concurrent / Repeat Diagnosis | ⬜ | |
| 5 | 5.1 | Create HA Group in Topology | ⬜ | |
| 5 | 5.2 | Verify HA in Knowledge Graph | ⬜ | |
| 6 | 6.1 | Add Cloud VPC | ⬜ | |
| 6 | 6.2 | Add AZ and Subnets | ⬜ | |
| 6 | 6.3 | Add Load Balancer | ⬜ | |
| 6 | 6.4 | Add VPN Tunnel | ⬜ | |
| 6 | 6.5 | Add Transit Gateway | ⬜ | |
| 6 | 6.6 | Add Compliance Zone | ⬜ | |
| 6 | 6.7 | Full Hybrid Path Diagnosis | ⬜ | |
| 7 | 7.1 | Navigate to Observatory | ⬜ | |
| 7 | 7.2 | Device Health Tab | ⬜ | |
| 7 | 7.3 | Live Topology Tab | ⬜ | |
| 7 | 7.4 | Traffic Flows Tab | ⬜ | |
| 7 | 7.5 | Alerts Tab | ⬜ | |
| 7 | 7.6 | Discovery Candidates | ⬜ | |
| 8 | 8.1 | Topology Editor Edge Cases | ⬜ | |
| 8 | 8.2 | IPAM Edge Cases | ⬜ | |
| 8 | 8.3 | Adapter Edge Cases | ⬜ | |
| 8 | 8.4 | Diagnosis Edge Cases | ⬜ | |
| 8 | 8.5 | Cross-Feature Flow | ⬜ | |
| 8 | 8.6 | Reachability Matrix | ⬜ | |
