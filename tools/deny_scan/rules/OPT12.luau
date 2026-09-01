-- OPT12 (dot-index clause): workspace.<Name> dot-index in a client tree —
-- streaming means the child may not exist yet. CurrentCamera and Terrain are
-- always present and excepted. The nil-check clause lives in style_assess.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "OPT12"

local function lint(ast, sourcepath, context)
	local entry = context.options or {}
	if not lib.inPaths(sourcepath, entry.paths) then
		return {}
	end
	local except = entry.except or { "CurrentCamera", "Terrain" }
	local remedy = entry.message or "WaitForChild or FindFirstChild + nil-check"
	local out = {}
	local v = visitor.create()
	v.visitExprIndexName = function(node)
		if
			node.accessor.text == "."
			and node.expression.tag == "global"
			and node.expression.name.text == "workspace"
			and not lib.inList(node.index.text, except)
		then
			table.insert(
				out,
				lib.violation(name, node.location, "workspace." .. node.index.text, remedy, sourcepath)
			)
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
