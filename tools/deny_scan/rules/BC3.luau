-- BC3: task.* only — never legacy wait / spawn / delay.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "BC3"

local function lint(ast, sourcepath, context)
	local entry = context.options or {}
	if not lib.inPaths(sourcepath, entry.paths) then
		return {}
	end
	local denied = entry.pattern or { "wait", "spawn", "delay" }
	local template = entry.message or "task.%s"
	local out = {}
	local v = visitor.create()
	v.visitExprGlobal = function(node)
		local text = node.name.text
		if lib.inList(text, denied) then
			table.insert(out, lib.violation(name, node.location, text, template:format(text, text), sourcepath))
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
