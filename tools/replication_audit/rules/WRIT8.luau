-- WRIT8: remotes only via m.Events / the Event package —
-- Instance.new("RemoteEvent"/"RemoteFunction") outside the Event package is a
-- guarantee on the literal class name.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "WRIT8"

local function lint(ast, sourcepath, context)
	local p = lib.pathString(sourcepath)
	if p:match("/Packages/Event%.luau$") or p:match("/Packages/Event%.lua$") or p:match("/Packages/Event/") then
		return {}
	end
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local f = node.func
		if f.tag == "indexname" and f.index.text == "new" and f.expression.tag == "global" and f.expression.name.text == "Instance" then
			local value = lib.stringValue(lib.nodes(node.arguments)[1])
			if value == "RemoteEvent" or value == "RemoteFunction" then
				table.insert(
					out,
					lib.violation(name, node.location, 'Instance.new("' .. value .. '")', "Declare the remote via m.Events + Event package; retry.", sourcepath)
				)
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
