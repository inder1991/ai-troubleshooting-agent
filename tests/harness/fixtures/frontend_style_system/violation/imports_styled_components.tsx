/* Q1 violation — styled-components banned. */
import styled from "styled-components";

const Card = styled.div`color: red;`;

export const Foo = () => <Card>x</Card>;
