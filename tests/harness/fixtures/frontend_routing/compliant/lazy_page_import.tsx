/* Q6 compliant — lazy-imported page in the route table.

Pretend-path: frontend/src/router.tsx
*/
import { lazy } from "react";
import { createBrowserRouter } from "react-router-dom";

const IncidentsPage = lazy(() => import("@/pages/Incidents"));

export const router = createBrowserRouter([
  { path: "/incidents", element: <IncidentsPage /> },
]);
