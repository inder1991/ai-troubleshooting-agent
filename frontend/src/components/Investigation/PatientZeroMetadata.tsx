import React from 'react';
import type { V4Findings } from '../../types';
import { lookupOwner, slackUrlFor } from '../../config/service_owners';

/**
 * Two additive lines rendered inside the Patient Zero banner, directly
 * below the evidence paragraph. Additive only — Patient Zero's existing
 * skin is untouched.
 *
 * Line 1 — env context (cluster · version · namespace). Each segment
 *          drops independently when its source is absent. If all three
 *          segments are absent, the line does not render.
 *
 * Line 2 — service owner ("owned by payments-platform"). Looked up from
 *          the static SERVICE_OWNERS config. If the service is not in
 *          the map, the line does not render. Never "owner unknown".
 *
 * Absence is the signal — the two lines together add 0–~20px of density
 * without ever shouting about missing data.
 */

interface PatientZeroMetadataProps {
  findings: V4Findings;
}

// ── Env context helpers ────────────────────────────────────────────

function deriveNamespace(findings: V4Findings): string | null {
  const ns = findings.pod_statuses?.[0]?.namespace?.trim();
  return ns && ns.length > 0 ? ns : null;
}

function deriveVersion(_findings: V4Findings): string | null {
  // Version is not yet provided by the backend on PatientZero. When
  // `patient_zero.service_version` lands (tracked separately), read it
  // here. For now the segment silently drops.
  return null;
}

function deriveCluster(_findings: V4Findings): string | null {
  // No cluster/region field on current PatientZero or session payload.
  // Segment drops until the backend enriches.
  return null;
}

// ── Component ──────────────────────────────────────────────────────

const PatientZeroMetadata: React.FC<PatientZeroMetadataProps> = ({ findings }) => {
  const cluster = deriveCluster(findings);
  const version = deriveVersion(findings);
  const namespace = deriveNamespace(findings);
  const envSegments = [cluster, version && `v${version}`, namespace && `ns/${namespace}`]
    .filter((s): s is string => !!s);

  const service = findings.patient_zero?.service;
  const owner = lookupOwner(service);

  // Both lines absent → render nothing.
  if (envSegments.length === 0 && !owner) return null;

  return (
    <div className="mt-1 space-y-0.5" data-testid="patient-zero-metadata">
      {envSegments.length > 0 && (
        <div
          className="text-[11px] font-mono text-slate-400"
          data-testid="patient-zero-env"
        >
          {envSegments.join(' · ')}
        </div>
      )}
      {owner && (
        <div
          className="text-[11px] font-mono text-slate-400"
          data-testid="patient-zero-owner"
        >
          {owner.slack ? (
            <>
              owned by{' '}
              <a
                href={slackUrlFor(owner.slack)}
                target="_blank"
                rel="noopener noreferrer"
                className="underline-offset-4 hover:underline text-slate-300"
                title={`Open ${owner.slack} in Slack`}
              >
                {owner.team}
              </a>
            </>
          ) : (
            <>owned by {owner.team}</>
          )}
        </div>
      )}
    </div>
  );
};

export default PatientZeroMetadata;
