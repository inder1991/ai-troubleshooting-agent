import { apiClient } from "./client";

export interface FooRequest { id: string; }
export interface FooResponse { name: string; }

export const fetchFoo = (id: string) =>
  apiClient<FooResponse>(`/api/v4/foo/${id}`, { method: "GET" });

export const createFoo = (body: FooRequest) =>
  apiClient<FooResponse>(`/api/v4/foo`, { method: "POST", body });
