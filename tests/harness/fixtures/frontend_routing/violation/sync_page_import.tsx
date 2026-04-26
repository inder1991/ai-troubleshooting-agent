/* Q6 violation — synchronous page import inside the route table.

Pretend-path: frontend/src/router.tsx
*/
import { createBrowserRouter } from "react-router-dom";
import IncidentsPage from "@/pages/Incidents";

export const router = createBrowserRouter([
  { path: "/incidents", element: <IncidentsPage /> },
]);
