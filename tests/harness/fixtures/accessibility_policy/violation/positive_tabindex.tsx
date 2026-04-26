/* Q14 violation — positive tabIndex creates focus-order trap. */
export const Foo = () => <div tabIndex={3}>x</div>;
