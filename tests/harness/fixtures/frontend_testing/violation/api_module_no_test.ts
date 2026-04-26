/* Q5 violation — services/api module without paired *.test.ts.

Pretend-path: frontend/src/services/api/orphan.ts
*/
export const fetchOrphan = () => fetch("/api/orphan");
