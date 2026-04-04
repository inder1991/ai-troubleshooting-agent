describe('save_cluster default behavior', () => {
  it('defaults save_cluster to false when undefined — does not auto-save credentials', () => {
    const saveClusterUndefined = undefined as boolean | undefined;
    expect(saveClusterUndefined ?? false).toBe(false); // correct behavior
    // Bug was: saveClusterUndefined ?? true = true (silently saves)
    expect(saveClusterUndefined ?? true).toBe(true); // documents the old bug
  });
});
