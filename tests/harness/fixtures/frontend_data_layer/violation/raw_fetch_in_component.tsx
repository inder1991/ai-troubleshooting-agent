/* Q3 violation — raw fetch() inside a component. */
import { useEffect, useState } from "react";

export const Foo = () => {
  const [data, setData] = useState<unknown>(null);
  useEffect(() => {
    fetch("/api/foo").then((r) => r.json()).then(setData);
  }, []);
  return <div>{JSON.stringify(data)}</div>;
};
