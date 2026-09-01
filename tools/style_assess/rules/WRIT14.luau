-- WRIT14: the final entry in a table constructor has no separator comma.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT14"

local function lint(ast, sourcepath, context)
	local out = {}
	local v = visitor.create()
	v.visitExprTable = function(node)
		local last = node.entries[#node.entries]
		if last ~= nil and last.separator ~= nil and last.separator.text == "," then
			table.insert(
				out,
				lib.violation(name, last.separator.location, "final table entry comma", "remove the final comma", sourcepath)
			)
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
