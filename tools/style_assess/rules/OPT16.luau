-- OPT16: workspace lookups only go in functions — a module-level lookup runs
-- before streaming settles.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "OPT16"

local function lint(ast, sourcepath, context)
	local out = {}
	local depth = 0
	local v = visitor.create()
	v.visitExprFunction = function(node)
		depth += 1
		return true
	end
	v.visitExprFunctionEnd = function(node)
		depth -= 1
	end
	v.visitExprIndexName = function(node)
		if depth == 0 and node.expression.tag == "global" and node.expression.name.text == "workspace" then
			table.insert(
				out,
				lib.violation(
					name,
					node.location,
					"workspace." .. node.index.text,
					"workspace lookups only go in functions",
					sourcepath
				)
			)
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
