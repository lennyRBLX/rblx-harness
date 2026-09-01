-- WRIT22 (--fix): double-quoted strings. Ships as suggestedfix + --auto-fix:
-- each edit touches one token and string literals never nest. Skips a literal
-- already containing a double quote — the finding still reports and a human
-- converts it.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT22"

local function lint(ast, sourcepath, context)
	local out = {}
	local v = visitor.create()
	v.visitExprConstantString = function(node)
		if node.quoteStyle == "single" then
			local content = node.token.text
			local violation = lib.violation(name, node.location, "single-quoted string", "double quotes", sourcepath)
			if not content:find('"', 1, true) then
				violation.suggestedfix = { fix = '"' .. content .. '"' }
			end
			table.insert(out, violation)
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
