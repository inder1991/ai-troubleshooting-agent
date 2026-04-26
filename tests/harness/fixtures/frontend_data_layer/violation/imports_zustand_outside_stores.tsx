/* Q2 violation — zustand outside frontend/src/stores/. */
import { create } from "zustand";

export const useFoo = create(() => ({ x: 1 }));
