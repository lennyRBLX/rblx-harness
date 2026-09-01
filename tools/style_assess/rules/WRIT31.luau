-- WRIT31: prefer BodyMover instances to Constraints; Torque excepted. The
-- house overrides the upstream deprecation — the class sets come from
-- api_dump through context.globals.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT31"

local function lint(ast, sourcepath, context)
	local constraints = (context.globals or {}).constraints
	if constraints == nil then
		return {}
	end
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local f = node.func
		if f.tag == "indexname" and f.index.text == "new" and f.expression.tag == "global" and f.expression.name.text == "Instance" then
			local args = lib.nodes(node.arguments)
			local value = lib.stringValue(args[1])
			if value ~= nil and constraints[value] and value ~= "Torque" then
				table.insert(
					out,
					lib.violation(name, node.location, 'Instance.new("' .. value .. '")', "prefer the BodyMover house form", sourcepath)
				)
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
