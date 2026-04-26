/* Q1 compliant — multi-class merging via cn(). */
import { cn } from "@/lib/utils";

export const Foo = ({ active }: { active: boolean }) => (
  <div className={cn("px-4 py-2", active ? "bg-amber-500" : "bg-slate-700")}>x</div>
);
