# Math-tool protocol v1

Read this reference only to build a request or correct a schema error. All wire
objects are compact JSON objects with `v: 1`. Unknown fields are invalid.

## Request

```json
{"ast":{"args":[{"type":"integer","value":"2"},{"type":"integer","value":"3"}],"type":"add"},"obligation":"<32 lowercase hex>","op":"evaluate","v":1}
```

The request fields are `v`, `obligation`, `op`, `ast`, and optional
`variables` and `options`. A solve request can use one relation node or a list
of at most 16 equality-relation nodes. Other operations use one node.
Command JSON is compact and canonical: sort every object key recursively, use
no spaces, and preserve array order. The gate compares the complete command
byte for byte.

## Typed AST

| Type | Required fields | Allowed values |
|---|---|---|
| `integer` | `value` | decimal integer or decimal string |
| `rational` | `numerator`, `denominator` | decimal integers; denominator is nonzero |
| `symbol` | `name` | ASCII identifier |
| `constant` | `name` | `pi`, `E`, `I`, `oo` |
| `add`, `multiply` | `args` | two or more nodes |
| `power` | `base`, `exponent` | two nodes |
| `function` | `name`, `args` | allowlisted function and nodes |
| `relation` | `op`, `left`, `right` | `eq`, `ne`, `lt`, `le`, `gt`, `ge` |
| `matrix` | `rows` | non-empty rectangular node rows |

Allowed functions are `abs`, `acos`, `asin`, `atan`, `cos`, `cosh`, `exp`,
`factorial`, `gamma`, `gcd`, `lcm`, `log`, `sin`, `sinh`, `sqrt`, `tan`, and
`tanh`. The tool does not accept expression strings, Python, arbitrary SymPy
names, `eval`, or general functions.

## Operation controls

- `evaluate`, `simplify`, `factor`, and `expand`: optional
  `options.precision` from 1 through 100.
- `solve`: one or more names in `variables`.
- `differentiate`: names in `variables`; optional matching positive integer
  `options.orders`.
- `integrate`: names in `variables`; optional matching `options.bounds`, where
  each item is `null` or `[lower_ast, upper_ast]`.
- `limit`: one name in `variables`, `options.point`, and optional
  `options.direction` equal to `+`, `-`, or `+-`.
- `matrix`: a matrix AST and `options.action` equal to `determinant`, `inverse`,
  `rank`, `rref`, `trace`, or `transpose`.
- `statistics`: a matrix AST and `options.action` equal to `mean`, `median`,
  `variance`, or `standard_deviation`; optional boolean `options.sample`.

## Result, receipt, and final answer

An accepted tool result has:

```json
{"canonical":"<visible result>","digest":"<sha256>","exact":"<exact result>","obligation":"<id>","status":"accepted","v":1}
```

It can also have `approximate`. A blocked result has `status: "blocked"` and a
`failure` object with `code` and `message`. The gate creates a receipt only for
an exact current-turn command, request, accepted result, runtime, and tool-use
identity. The final answer is accepted only when it shows the receipt's exact
`canonical` value and `[math-tool:v1:<obligation>:<digest>]` marker.

## Limits

The limits are one obligation and receipt per turn; one normal call and one
repair call; one Stop continuation; 8,192 request bytes; 256 AST nodes; depth
24; 1,000 integer digits; 32 symbols; 16 equations; 256 matrix cells; 100
digits of precision; five compute seconds; 2,048 result bytes; 512 result
tokens; and 96 diagnostic tokens. Search, delegation, and added model routes
are not part of this workflow.

State is bound to host, session, turn or obligation, protocol, classifier,
skill digest, tool digest, runtime-lock digest, and SymPy version. Hooks do not
grant tool permission or change normal approval requirements.
