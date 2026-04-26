/* Q14 violation — primitive paired test does not call axe().

Pretend-path: frontend/src/components/ui/badge.test.tsx
*/
import { render } from "@testing-library/react";
import { Badge } from "./badge";

test("renders", () => {
  render(<Badge>x</Badge>);
});
