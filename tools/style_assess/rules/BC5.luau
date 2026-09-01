-- BC5 (casing ladder): public PascalCase under `-- functions`, private
-- camelCase under `-- privates`; private fields __camelCase, private
-- attributes _PascalCase. Tabs are the formatter's clause.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "BC5"

local function lint(ast, sourcepath, context)
	local out = {}
	local divs = lib.dividers(ast)
	if next(divs) == nil then
		return out -- no sanctioned dividers; section casing has no anchor
	end

	local v = visitor.create()
	v.visitStatFunction = function(node)
		local fname = node.name
		if fname.tag == "indexname" then
			local method = fname.index.text
			local section = lib.sectionOf(node.location.beginLine, divs)
			if section == "functions" and method:match("^%l") then
				table.insert(
					out,
					lib.violation(name, fname.indexLocation, method, "public methods are PascalCase under -- functions", sourcepath)
				)
			elseif section == "privates" and method:match("^%u") then
				table.insert(
					out,
					lib.violation(name, fname.indexLocation, method, "private methods are camelCase under -- privates", sourcepath)
				)
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
