import * as React from "react";
import * as RadixSlot from "@radix-ui/react-slot";

export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ ...props }, ref) => <button ref={ref} {...props} />,
);
Button.displayName = "Button";

export const Spacer = () => <div className="w-2" />;
