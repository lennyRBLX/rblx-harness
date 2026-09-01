---
name: math-tool
description: Use for supported arithmetic, algebra, calculus, matrix, statistics, number-theory, geometry, and trigonometry computations. Do not use for code changes, quoted examples, or requests that do not require a computed math result.
---

# Math Tool

When `MATH_TOOL_GATE:v1:<obligation>` is present, complete that obligation with
the pinned tool. Do not substitute mental arithmetic, another calculator,
search, or delegation.

1. Build one protocol-v1 request and run the exact command supplied by the
   gate. Encode compact canonical JSON: sort every object key recursively, use
   no spaces, and preserve array order. Keep `obligation` unchanged. Use one
   normal call; use the one repair call only when gate feedback requests it.
2. Build expressions only with these typed nodes:
   `integer(value)`, `rational(numerator,denominator)`, `symbol(name)`,
   `constant(name)`, `add(args)`, `multiply(args)`,
   `power(base,exponent)`, `function(name,args)`,
   `relation(op,left,right)`, and `matrix(rows)`.
3. Select one operation: `evaluate`, `simplify`, `solve`, `differentiate`,
   `integrate`, `limit`, `factor`, `expand`, `matrix`, or `statistics`.
   Supply symbol names in `variables` and operation controls in `options`.
4. After an accepted tool result, use its `canonical` value unchanged in the
   visible answer and include this exact marker:
   `[math-tool:v1:<obligation>:<digest>]`.

Keep the explanation short. Do not show private reasoning or tool logs. If the
gate reports a schema error, read [references/protocol.md](references/protocol.md)
and correct only the request or command it identifies. If the repair budget is
exhausted, report `status: blocked` and the typed failure.
