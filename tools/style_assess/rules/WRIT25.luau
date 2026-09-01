-- WRIT25: GetService takes a real service name — the list comes from api_dump
-- through context.globals, never hardcoded.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT25"

local function lint(ast, sourcepath, context)
	local services = (context.globals or {}).services
	if services == nil or #services == 0 then
		return {}
	end
	local known = {}
	for _, s in services do
		known[s] = true
	end
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local method, f = lib.methodCall(node)
		if method == "GetService" and f.expression.tag == "global" and f.expression.name.text == "game" then
			local args = lib.nodes(node.arguments)
			local value = lib.stringValue(args[1])
			if value ~= nil and not known[value] then
				table.insert(out, lib.violation(name, args[1].location, value, "not a service in the api dump", sourcepath))
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
