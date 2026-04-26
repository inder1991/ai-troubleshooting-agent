/* Q2/Q3 compliant — hook wraps apiClient, component consumes hook. */
import { useIncident } from "@/hooks/useIncident";

export const Foo = ({ id }: { id: string }) => {
  const { data } = useIncident(id);
  return <div>{data?.summary ?? "loading"}</div>;
};
