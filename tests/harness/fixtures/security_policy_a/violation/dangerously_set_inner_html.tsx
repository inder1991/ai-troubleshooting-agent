/* Q13 violation — dangerouslySetInnerHTML banned (XSS vector). */
export const Foo = ({ html }: { html: string }) => (
  <div dangerouslySetInnerHTML={{ __html: html }} />
);
