/* Q5 violation — vitest import in e2e file.

Pretend-path: frontend/e2e/login.spec.ts
*/
import { describe, it } from "vitest";

describe("login", () => it("works", () => {}));
