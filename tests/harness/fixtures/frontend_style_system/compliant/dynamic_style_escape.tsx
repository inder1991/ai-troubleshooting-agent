/* Q1 compliant — inline style permitted only for dynamic geometry props. */
export const Bar = ({ widthPx }: { widthPx: number }) => (
  <div style={{ width: widthPx }} className="h-2 bg-amber-500" />
);
