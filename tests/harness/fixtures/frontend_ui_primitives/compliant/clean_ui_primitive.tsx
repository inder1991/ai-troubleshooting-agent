/* Q4 compliant — primitive lives under ui/, no business imports.

Pretend-path: frontend/src/components/ui/button.tsx
*/
import * as React from "react";
import { cn } from "@/lib/utils";

export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ className, ...props }, ref) => (
    <button ref={ref} className={cn("inline-flex items-center", className)} {...props} />
  ),
);
Button.displayName = "Button";
