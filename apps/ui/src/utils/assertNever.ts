// Use in a switch's `default:` (or after a chain of conditionals) to enforce
// exhaustive handling of a discriminated union. If a new variant is added to
// the union, TypeScript will narrow `value` to something other than `never`
// and the call site stops compiling — surfacing the omission instead of
// silently falling through to a default branch.
export function assertNever(value: never): never {
  throw new Error(`Unhandled discriminant: ${JSON.stringify(value)}`);
}
