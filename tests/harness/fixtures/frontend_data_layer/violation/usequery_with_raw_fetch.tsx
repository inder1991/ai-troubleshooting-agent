/* Q3 violation — useQuery queryFn calls raw fetch(). */
import { useQuery } from "@tanstack/react-query";

export const Foo = () =>
  useQuery({ queryKey: ["x"], queryFn: () => fetch("/api/x").then((r) => r.json()) });
