/* Q1 violation — classNames merged via + or template literal, not cn(). */
export const Foo = ({ active }: { active: boolean }) => (
  <div className={"px-4 py-2 " + (active ? "bg-amber-500" : "bg-slate-700")}>x</div>
);
