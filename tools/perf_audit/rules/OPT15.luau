-- OPT15: explicit parallel scopes close on every exit; infer writes only in
-- the advisory performance pass. Exact API safety remains engine evidence.
local flow = require("../flow")
local function lint(ast, sourcepath, context)
	return flow.lint(ast, sourcepath, "parallel", true)
end
return table.freeze({ name = "OPT15", lint = lint })
