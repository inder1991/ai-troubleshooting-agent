/* Q3 violation — component imports services/api directly. */
import { fetchIncident } from "@/services/api/incidents";

export const Foo = () => {
  fetchIncident("x");
  return <div />;
};
