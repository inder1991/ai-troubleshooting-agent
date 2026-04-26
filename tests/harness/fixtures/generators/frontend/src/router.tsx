import { lazy } from "react";
import { createBrowserRouter } from "react-router-dom";
import HomePage from "@/pages/Home";

const IncidentsPage = lazy(() => import("@/pages/Incidents"));
const SettingsPage = lazy(() => import("@/pages/Settings"));

export const router = createBrowserRouter([
  { path: "/", element: <HomePage /> },
  { path: "/incidents", element: <IncidentsPage /> },
  { path: "/settings", element: <SettingsPage /> },
]);
