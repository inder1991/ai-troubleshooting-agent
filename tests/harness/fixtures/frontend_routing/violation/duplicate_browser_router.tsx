/* Q6 violation — additional createBrowserRouter call outside router.tsx.

Pretend-path: frontend/src/components/AdminRouter.tsx
*/
import { createBrowserRouter } from "react-router-dom";

export const router = createBrowserRouter([{ path: "/admin", element: null }]);
