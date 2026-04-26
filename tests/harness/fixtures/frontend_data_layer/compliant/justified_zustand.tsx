/* Q2 compliant — zustand inside frontend/src/stores/ with justification. */
// JUSTIFICATION: cross-route UI state for War Room layout density.
import { create } from "zustand";

export const useLayoutStore = create<{ density: "compact" | "comfortable" }>(() => ({
  density: "comfortable",
}));
