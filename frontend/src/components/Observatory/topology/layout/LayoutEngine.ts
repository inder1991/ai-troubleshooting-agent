import type { LayoutInput, LayoutOutput, LayoutAlgorithm } from './types';
import { hierarchicalLayout } from './hierarchical';
import { forceDirectedLayout } from './forceDirected';

export function computeLayout(input: LayoutInput): LayoutOutput {
  switch (input.algorithm) {
    case 'force_directed':
      return forceDirectedLayout(input);
    case 'hierarchical':
      return hierarchicalLayout(input);
    case 'radial':
      return hierarchicalLayout(input); // fallback to hierarchical for now
    case 'geographic':
      return hierarchicalLayout(input); // fallback to hierarchical for now
    default:
      return hierarchicalLayout(input);
  }
}

export function recommendAlgorithm(nodeCount: number, hasGeo: boolean = false): LayoutAlgorithm {
  if (hasGeo) return 'geographic';
  if (nodeCount <= 50) return 'force_directed';
  return 'hierarchical';
}

export { type LayoutAlgorithm, type LayoutInput, type LayoutOutput } from './types';
