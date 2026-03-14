# Diagnostic Intelligence Engine — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 6 deterministic pipeline stages (signal normalizer, pattern matcher, temporal analyzer, diagnostic graph, lifecycle classifier, hypothesis engine) plus enhanced critic, solution validator, and frontend UI overhaul to the cluster diagnostics pipeline.

**Architecture:** Layered deterministic nodes inserted between domain agents and synthesizer in the LangGraph state machine. LLM becomes the last step (explain + remediate), not the main reasoning engine. Frontend rebuilt around prioritized issue tiers and hypothesis cards.

**Tech Stack:** Python/Pydantic (backend models), LangGraph (orchestration), React/TypeScript/Tailwind (frontend)

**Design doc:** `docs/plans/2026-03-15-diagnostic-intelligence-design.md` — contains all data models, algorithms, and UI specifications.

---

## Task 1: State Models

**Files:**
- Modify: `backend/src/agents/cluster/state.py`

Add all new Pydantic models from design doc Section 1-4 to the existing state.py. Models to add:

- `NormalizedSignal` — signal_id, signal_type, resource_key, source_domain, raw_value, reliability, timestamp, namespace
- `FailurePattern` — pattern_id, name, version, scope, priority, conditions, probable_causes, known_fixes, severity, confidence_boost
- `PatternMatch` — pattern_id, name, matched_conditions, affected_resources, confidence_boost, severity, scope, probable_causes, known_fixes
- `DiagnosticNode` — node_id, node_type, resource_key, signal_type, severity, reliability, first_seen, last_seen, event_age_seconds, restart_velocity, resource_age_seconds, event_count_recent, event_count_baseline, namespace
- `DiagnosticEdge` — from_id, to_id, edge_type, confidence, evidence
- `DiagnosticGraph` — nodes dict, edges list
- `IssueState` enum — 9 states (ACTIVE_DISRUPTION through ACKNOWLEDGED)
- `LifecycleThresholds` — tunable config knobs (active_event_age_seconds, worsening_rate_multiplier, etc.)
- `DiagnosticIssue` — issue_id, state, priority_score, first_seen, last_state_change, state_duration_seconds, event_count_recent/baseline, restart_velocity, severity_trend, is_root_cause, is_symptom, root_cause_id, blast_radius, affected_resources, signals, pattern_matches, anomaly_ids
- `WeightedEvidence` — signal_id, signal_type, resource_key, weight, reliability, relevance
- `Hypothesis` — hypothesis_id, cause, cause_type, source, supporting/contradicting evidence, scores, affected_issues, explains_count, blast_radius, root_resource, causal_chain, depth, evidence_ids
- `SimulationResult` — action, target, impact, side_effects, recovery
- `SolutionValidation` — risk_level, warnings, requires_confirmation, blocked, block_reason, simulation, remediation_confidence, confidence_label

Also update `ClusterHealthReport` to add: critical_incidents, other_findings, symptom_map, ranked_hypotheses, hypothesis_selection, pattern_matches_count, signals_count, diagnostic_graph_node_count, diagnostic_graph_edge_count, issue_lifecycle_summary.

**Commit:** `feat(state): add diagnostic intelligence models`

---

## Task 2: Signal Normalizer

**Files:**
- Create: `backend/src/agents/cluster/signal_normalizer.py`

Implement `extract_signals(reports)` function and `signal_normalizer` traced node (3s timeout).

Signal extraction rules from design doc Section 1:
- Pod status CrashLoopBackOff → CRASHLOOP (0.8)
- Pod status OOMKilled → OOM_KILLED (0.9)
- Node DiskPressure → NODE_DISK_PRESSURE (1.0)
- Deployment replicas_ready < desired → DEPLOYMENT_DEGRADED (0.9)
- Service endpoints == 0 → SERVICE_ZERO_ENDPOINTS (0.9)
- Event reason FailedScheduling → FAILED_SCHEDULING (0.6)
- HPA scaling_limited → HPA_AT_MAX (0.9)
- PVC phase Pending → PVC_PENDING (0.9)
- Pod restarts > 5 → HIGH_RESTART_COUNT (0.8)
- DaemonSet number_unavailable > 0 → DAEMONSET_INCOMPLETE (0.9)

Parse domain_reports, extract anomalies and data payloads, normalize into NormalizedSignal objects with signal_id (uuid), reliability, resource_key, timestamp.

Returns: `{"normalized_signals": [signal.model_dump() for signal in signals]}`

**Commit:** `feat(cluster): add signal normalizer`

---

## Task 3: Failure Pattern Library + Matcher

**Files:**
- Create: `backend/src/agents/cluster/failure_patterns.py`

Implement:
1. `FAILURE_PATTERNS` list — 15 FailurePattern instances from design doc Section 1
2. `match_patterns(reports, signals, patterns)` — iterate patterns, check if all conditions match against signal set, return PatternMatch list
3. `resolve_priority_conflicts(matches)` — when multiple patterns match same resource, keep highest priority
4. `failure_pattern_matcher` traced node (5s timeout)

Pattern condition matching logic: for each pattern, check if every condition's signal type exists in the normalized_signals for overlapping resources.

Returns: `{"pattern_matches": [match.model_dump() for match in matches]}`

**Commit:** `feat(cluster): add failure pattern library with 15 patterns`

---

## Task 4: Temporal Analyzer

**Files:**
- Create: `backend/src/agents/cluster/temporal_analyzer.py`

Implement:
1. `compute_temporal_attributes(signals, domain_reports)` — for each signal, compute event_age_seconds, resource_age_seconds, restart_velocity, event_count_recent (5 min window), event_count_baseline (60 min window) from K8s event timestamps
2. `detect_worsening(node)` — event rate spike (>3x baseline), restart velocity acceleration, cascade growth
3. `detect_flapping(events)` — count state toggles within window
4. `temporal_analyzer` traced node (3s timeout)

Returns: `{"temporal_analysis": temporal_data_dict}` — enriches normalized_signals with temporal attributes.

**Commit:** `feat(cluster): add temporal analyzer with worsening detection`

---

## Task 5: Diagnostic Graph Builder

**Files:**
- Create: `backend/src/agents/cluster/diagnostic_graph_builder.py`

Implement:
1. `build_diagnostic_graph(signals, topology, pattern_matches, temporal_data)` — creates DiagnosticGraph from signals as nodes + deterministic edge rules
2. Edge creation rules from design doc Section 2:
   - Node pressure + pod eviction on same node → CAUSES
   - Deployment owns evicted pods → AFFECTS
   - Service selector matches degraded deployment → DEPENDS_ON
   - Two signals share resource_key → OBSERVED_AFTER (temporal)
   - Pattern match links signals → SYMPTOM_OF
3. `bfs_reachable(graph, start_node)` — BFS for reachability checks
4. `graph_has_path(graph, from_id, to_id)` — path existence check
5. `diagnostic_graph_builder` traced node (5s timeout)

Returns: `{"diagnostic_graph": graph.model_dump()}`

**Commit:** `feat(cluster): add diagnostic evidence graph builder`

---

## Task 6: Issue Lifecycle Classifier

**Files:**
- Create: `backend/src/agents/cluster/issue_lifecycle.py`

Implement:
1. `classify_issue_state(issue, thresholds)` — ordered evaluation from design doc Section 2 (SYMPTOM → ACTIVE_DISRUPTION → WORSENING → INTERMITTENT → NEW → LONG_STANDING → EXISTING)
2. `compute_priority_score(issue)` — STATE_WEIGHT + SEVERITY_WEIGHT + blast_radius + root_cause bonus
3. `build_diagnostic_issues(diagnostic_graph, signals, pattern_matches, thresholds)` — group signals into issue clusters, classify each, sort by priority
4. `issue_lifecycle_classifier` traced node (5s timeout)
5. `LifecycleThresholds` config loaded from config dict

Returns: `{"diagnostic_issues": [issue.model_dump() for issue in sorted_issues]}`

**Commit:** `feat(cluster): add 9-state issue lifecycle classifier`

---

## Task 7: Hypothesis Engine

**Files:**
- Create: `backend/src/agents/cluster/hypothesis_engine.py`

Implement:
1. `hypotheses_from_patterns(pattern_matches)` — each PatternMatch → Hypothesis at 0.5 + confidence_boost
2. `hypotheses_from_graph(diagnostic_graph)` — root nodes (outgoing CAUSES, no incoming CAUSES) → Hypothesis
3. `hypotheses_from_correlation(signals, diagnostic_graph)` — signals sharing topology dependency + namespace + temporal proximity (<60s)
4. `collect_negative_evidence(hypothesis, all_signals, ruled_out)` — CONTRADICTION_RULES + ruled_out matching
5. `score_hypothesis(h)` — capped evidence - contradiction + explanatory bonus + diversity bonus - depth penalty, logistic normalization
6. `deduplicate_hypotheses(hypotheses)` — merge by (resource_key, signal_family)
7. `filter_and_cap(hypotheses)` — drop below MIN_EVIDENCE_SCORE (0.4), cap MAX_HYPOTHESES_PER_ISSUE (3), MAX_TOTAL_HYPOTHESES (8)
8. `determine_root_causes(ranked)` — deterministic if gap > 0.15, else LLM disambiguation
9. `hypothesis_engine` traced node (10s timeout)

Returns: `{"ranked_hypotheses": [...], "hypotheses_by_issue": {...}, "hypothesis_selection": {...}}`

**Commit:** `feat(cluster): add multi-hypothesis root cause engine`

---

## Task 8: Enhanced Critic

**Files:**
- Modify: `backend/src/agents/cluster/critic_agent.py`

Replace current 3-check critic with 6-layer validation from design doc Section 4:

1. Evidence traceable — every supporting signal exists in normalized_signals
2. Resource exists — root_resource exists in topology
3. Causal chain valid — every edge in chain exists in diagnostic graph
4. Contradiction ratio — contradicting > supporting → REJECTED (>1.0), WEAKENED (>0.5)
5. Temporal consistency — root cause first_seen <= downstream first_seen
6. Graph reachability — root resource can reach all affected issues via BFS

Input: ranked_hypotheses, normalized_signals, diagnostic_graph, topology
Output: critic_result with validations, dropped/weakened hypothesis IDs

Keep the traced_node decorator but increase timeout to 8s.

**Commit:** `feat(cluster): enhance critic with 6-layer hypothesis validation`

---

## Task 9: Solution Validator

**Files:**
- Modify: `backend/src/agents/cluster/command_validator.py`

Add to existing command_validator:

1. `FORBIDDEN_COMMANDS` list — delete namespace/node/pvc/pv/clusterrole/crd/storageclass, replace --force
2. `check_forbidden(command)` → (blocked, reason)
3. `OWNER_BEHAVIOR` dict — ReplicaSet/DaemonSet/StatefulSet = safe, Job = may_not_restart, None = permanent_delete
4. `simulate_command(command, topology, domain_reports)` → SimulationResult (impact, side_effects, recovery)
5. `check_replica_safety(command, domain_reports)` — pod delete when deployment replicas=1
6. `check_drain_capacity(command, topology)` — draining 1-of-2 nodes
7. `check_fixes_root_cause(step, hypothesis_selection)` — destructive action on non-root resource
8. `compute_remediation_confidence(step, hypothesis, simulation, risk)` → 0.0-1.0 score
9. `validate_solution(step, topology, domain_reports, hypothesis)` — runs all checks, returns step with validation dict

**Also create the solution_validator graph node:**
- Create: `backend/src/agents/cluster/solution_validator.py`

```python
@traced_node(timeout_seconds=8)
async def solution_validator(state, config):
    # Read health_report remediation, validate each step
    # Return updated health_report with validation results
```

**Commit:** `feat(cluster): add solution validator with simulation and forbidden commands`

---

## Task 10: Graph Wiring + Synthesizer Updates

**Files:**
- Modify: `backend/src/agents/cluster/graph.py`
- Modify: `backend/src/agents/cluster/synthesizer.py`

**graph.py changes:**
1. Add new state fields: normalized_signals, pattern_matches, temporal_analysis, diagnostic_graph, diagnostic_issues, ranked_hypotheses, hypotheses_by_issue, hypothesis_selection
2. Import all 6 new nodes + solution_validator + enhanced_critic
3. Add all new nodes to graph
4. Rewire edges: domain agents → signal_normalizer → pattern_matcher → temporal_analyzer → graph_builder → lifecycle_classifier → hypothesis_engine → enhanced_critic → synthesize → solution_validator → conditional redispatch / guard_formatter
5. Remove old edges from domain agents directly to critic_validator

**synthesizer.py changes:**
1. Read ranked_hypotheses and hypothesis_selection from state
2. If `llm_reasoning_needed == False`: LLM only explains + generates remediation (doesn't pick root cause)
3. If `llm_reasoning_needed == True`: LLM disambiguates between close candidates
4. Build tiered output: critical_incidents (max 3), other_findings, symptom_map
5. Update LLM prompt to receive pre-ranked hypotheses instead of raw anomalies
6. Batch symptom fixes to root cause

**Commit:** `feat(cluster): rewire graph with diagnostic intelligence pipeline`

---

## Task 11: Frontend Types

**Files:**
- Modify: `frontend/src/types/index.ts`

Add TypeScript types:
- `IssueLifecycleState` — 9 string literal union
- `DiagnosticIssue` — issue_id, state, priority_score, first_seen, blast_radius, is_root_cause, is_symptom, root_cause_id, affected_resources, severity_trend, anomaly_ids
- `RankedHypothesis` — hypothesis_id, cause, confidence, source, supporting_count, contradicting_count, explains_count, causal_chain, depth, root_resource
- `SolutionValidation` — risk_level, warnings, requires_confirmation, blocked, block_reason, simulation (action/target/impact/side_effects/recovery), remediation_confidence, confidence_label
- Update `ClusterHealthReport` — add critical_incidents, other_findings, symptom_map, ranked_hypotheses, issue_lifecycle_summary, diagnostic_issues
- Update `ClusterRemediationStep` — add validation?: SolutionValidation

**Commit:** `feat(frontend): add diagnostic intelligence types`

---

## Task 12: IssuePriorityPanel + LifecycleSummaryStrip

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/IssuePriorityPanel.tsx`
- Create: `frontend/src/components/ClusterDiagnostic/LifecycleSummaryStrip.tsx`

**IssuePriorityPanel:** Tiered view grouped by lifecycle state. Derive from domain_reports + causal_chains until diagnostic_issues is available from backend. Each tier: distinct left-border color, distinct typography weight. Active=red/bold, Escalating=amber/normal, Known=slate/muted, Symptoms=italic/linked.

**LifecycleSummaryStrip:** Single 36px row replacing MetricCards grid. Colored dots + counts per lifecycle state. Right side: domain count + data completeness.

See design doc Section 6, Fix 1 and Fix 2 for full specifications.

**Commit:** `feat(frontend): add IssuePriorityPanel and LifecycleSummaryStrip`

---

## Task 13: HypothesisCard + ExecutionProgress

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/HypothesisCard.tsx`
- Create: `frontend/src/components/ClusterDiagnostic/ExecutionProgress.tsx`

**HypothesisCard:** Replaces RootCauseCard + VerdictStack. Shows ranked hypotheses with confidence bars, evidence counts, causal chain depth, source. Cascading effects collapsible within the card. Works with current data model (causal_chains) until hypotheses are available from backend.

**ExecutionProgress:** Merges ExecutionDAG + AgentTimeline into one component. DAG nodes with inline duration bars. Fixes agent count (5 not 4).

See design doc Section 6, Fix 4 and Fix 5.

**Commit:** `feat(frontend): add HypothesisCard and ExecutionProgress`

---

## Task 14: ClusterWarRoom Overhaul + RemediationCard + Cleanups

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/RemediationCard.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/FleetHeatmap.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/VerticalRibbon.tsx`
- Delete: `frontend/src/components/ClusterDiagnostic/NeuralPulseSVG.tsx`
- Delete: `frontend/src/components/ClusterDiagnostic/ResourceVelocity.tsx`

**ClusterWarRoom.tsx:**
- Remove imports: NeuralPulseSVG, ResourceVelocity, MetricCard, RootCauseCard, VerdictStack, ExecutionDAG, AgentTimeline
- Add imports: IssuePriorityPanel, LifecycleSummaryStrip, HypothesisCard, ExecutionProgress
- Remove `crt-scanlines` class
- Replace Domain Health Ribbon with LifecycleSummaryStrip
- Add `centerView` state: `'priority' | ClusterDomainKey` defaulting to `'priority'`
- Center column: IssuePriorityPanel when centerView='priority', DomainPanel when domain selected
- Left column: ExecutionProgress + FleetHeatmap (no ResourceVelocity)
- Right column: HypothesisCard + RemediationCard + ScanDiff

**RemediationCard.tsx:**
- Add simulation preview section before hold-to-execute button
- Add remediation_confidence badge (green >= 0.8, amber >= 0.5, gray >= 0.3)
- If validation.blocked, show block_reason and hide execute button
- If validation.requires_confirmation, show warning modal

**FleetHeatmap.tsx:**
- Remove 60-node placeholder grid for empty state
- Show "Waiting for node data" text instead

**VerticalRibbon.tsx:**
- Add lifecycle-colored dot (red/amber/slate) instead of just anomaly count
- Add "Priority" tab that switches centerView back to 'priority'

Standardize backgrounds: `bg-[#141210]` consistently, not mixed `bg-[#152a2f]/40`.

**Commit:** `feat(frontend): overhaul ClusterWarRoom with priority-driven layout`

---

## Task 15: API Updates + Lifecycle Config

**Files:**
- Modify: `backend/src/api/routes_v4.py`

1. Update `/session/{id}/findings` response to include: diagnostic_issues, issue_lifecycle_summary, ranked_hypotheses, critical_incidents, other_findings, symptom_map
2. Add `GET /cluster/lifecycle-config` → return default LifecycleThresholds
3. Add `PUT /cluster/lifecycle-config` → update thresholds (store in module-level variable)

**Commit:** `feat(api): add lifecycle config endpoints and enriched findings response`

---

## Implementation Order

Tasks 1-9 are backend, can be parallelized in groups:
- **Group A (independent):** Tasks 1, 2, 3, 4 — state models, signal normalizer, patterns, temporal
- **Group B (depends on A):** Tasks 5, 6 — diagnostic graph + lifecycle (need signals + patterns + temporal)
- **Group C (depends on B):** Task 7 — hypothesis engine (needs graph + lifecycle)
- **Group D (depends on C):** Tasks 8, 9 — enhanced critic + solution validator (need hypotheses)
- **Group E (depends on D):** Task 10 — graph wiring + synthesizer (integrates everything)

Tasks 11-14 are frontend, can be parallelized:
- **Group F (independent):** Tasks 11, 12, 13 — types + new components
- **Group G (depends on F):** Task 14 — ClusterWarRoom overhaul

Task 15 (API) depends on Tasks 1 + 10.

**Recommended execution:** Groups A → B → C → D → E in sequence. Groups F + G in parallel with backend. Task 15 last.
