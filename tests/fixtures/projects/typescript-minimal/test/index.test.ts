import { greeting } from "../src/index.ts";

if (greeting !== "hello") {
  throw new Error("unexpected greeting");
}
