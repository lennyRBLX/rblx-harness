-- WRIT18: no getfenv, setfenv, loadstring, setmetatable, newproxy in game
-- code. setmetatable and newproxy are the only two metatable constructors and
-- both are denied; getfenv/setfenv double-report as luau-lsp DeprecatedApi at
-- done-gate, and deny_scan blocks first so the house id wins.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "WRIT18"

local function lint(ast, sourcepath, context)
	local entry = context.options or {}
	if not lib.inPaths(sourcepath, entry.paths) then
		return {}
	end
	local denied = entry.pattern or { "getfenv", "setfenv", "loadstring", "setmetatable", "newproxy" }
	local remedy = entry.message or "denied in game code"
	local out = {}
	local v = visitor.create()
	v.visitExprGlobal = function(node)
		local text = node.name.text
		if lib.inList(text, denied) then
			table.insert(out, lib.violation(name, node.location, text, remedy, sourcepath))
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
