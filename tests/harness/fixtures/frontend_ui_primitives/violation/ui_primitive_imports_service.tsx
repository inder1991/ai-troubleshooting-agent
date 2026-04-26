/* Q4 violation — primitive imports business logic.

Pretend-path: frontend/src/components/ui/button.tsx
*/
import { fetchIncident } from "@/services/api/incidents";

export const Button = () => {
  fetchIncident("x");
  return <button />;
};
