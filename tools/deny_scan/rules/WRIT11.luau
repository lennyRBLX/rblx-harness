-- WRIT11: remote names are bare intents — never Request<X>. A lean: the
-- Request prefix is one shape of "named by intent" and the only statically
-- checkable one.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "WRIT11"

local function lint(ast, sourcepath, context)
	local entry = context.options or {}
	if not lib.inPaths(sourcepath, entry.paths) then
		return {}
	end
	local patterns = entry.pattern or { "^Request%u" }
	local remedy = entry.message or "remotes named by intent"
	local out = {}
	local v = visitor.create()
	v.visitExprConstantString = function(node)
		local value = lib.stringValue(node)
		if value ~= nil then
			for _, pat in patterns do
				if value:find(pat) then
					table.insert(out, lib.violation(name, node.location, value, remedy, sourcepath))
					break
				end
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
