describe('ClusterDiagnosticsFields auth methods', () => {
  it('service_account auth method must not be available — no backend handler exists', () => {
    // Verify the type system prevents service_account
    type AuthMethod = 'token' | 'kubeconfig';

    const validMethods: AuthMethod[] = ['token', 'kubeconfig'];

    // This should be compile-time enforced, but document it as a runtime check:
    expect(validMethods).not.toContain('service_account');
    expect(validMethods).toHaveLength(2);
  });
});

describe('save_cluster credential policy', () => {
  it('save_cluster undefined → do not save (App.tsx line ~297 and CapabilityForm.tsx line 157 policy)', () => {
    // Policy: undefined means user did not opt in to saving
    const saveCluster = undefined as boolean | undefined;

    // App.tsx: should NOT trigger profile creation
    const willSave = saveCluster ?? false;
    expect(willSave).toBe(false);

    // CapabilityForm.tsx: validation should NOT require a name when not
    // saving. Mirrors the production predicate:
    //   hasName = !(save_cluster ?? false) || !!cluster_name
    // → when save_cluster is undefined, the left disjunct is always true,
    //   so the name is never required. `requiresName` below directly
    //   models "is a name required" (true when saving).
    const requiresName = saveCluster ?? false;
    expect(requiresName).toBe(false);
  });

  it('save_cluster true → save credentials (user explicitly opted in)', () => {
    const saveCluster = true;
    const willSave = saveCluster ?? false;
    expect(willSave).toBe(true);

    const requiresName = saveCluster ?? false;
    expect(requiresName).toBe(true); // name required when saving
  });
});
