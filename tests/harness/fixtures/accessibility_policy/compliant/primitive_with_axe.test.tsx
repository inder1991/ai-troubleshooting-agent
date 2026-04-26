/* Q14 compliant — paired test calls axe().

Pretend-path: frontend/src/components/ui/button.test.tsx
*/
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { Button } from "./button";

test("button is a11y-clean", async () => {
  const { container } = render(<Button>x</Button>);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
