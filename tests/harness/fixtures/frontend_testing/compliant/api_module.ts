/* Q5 compliant — has paired test file in same fixture set.

Pretend-path: frontend/src/services/api/foo.ts
*/
import { apiClient } from "@/services/api/client";
export const fetchFoo = (id: string) => apiClient<{ id: string }>(`/api/foo/${id}`);
