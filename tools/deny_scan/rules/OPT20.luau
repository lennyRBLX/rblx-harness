-- Shared with the performance checker; correctness checks pairing only.
local flow = require("../../perf_audit/flow")
local function lint(ast, sourcepath, context)
	return flow.lint(ast, sourcepath, "profile", false)
end
return table.freeze({ name = "OPT20", lint = lint })
