-- WRIT30: Instance.new errors on a NotCreatable class; :Clone returns nil on
-- Archivable = false. The class set comes from api_dump through
-- context.globals.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT30"

local function lint(ast, sourcepath, context)
	local notcreatable = (context.globals or {}).notcreatable
	if notcreatable == nil then
		return {}
	end
	local out = {}
	local archivableOff = {}

	local v = visitor.create()
	v.visitStatAssign = function(node)
		for i, pair in node.variables do
			local target = pair.node
			if target.tag == "indexname" and target.index.text == "Archivable" then
				local valuePair = node.values[i]
				if valuePair and valuePair.node.tag == "boolean" and valuePair.node.value == false then
					local recv = lib.chainText(target.expression)
					if recv then
						archivableOff[recv] = true
					end
				end
			end
		end
		return true
	end
	v.visitExprCall = function(node)
		local f = node.func
		if f.tag == "indexname" and f.index.text == "new" and f.expression.tag == "global" and f.expression.name.text == "Instance" then
			local args = lib.nodes(node.arguments)
			local value = lib.stringValue(args[1])
			if value ~= nil and notcreatable[value] then
				table.insert(
					out,
					lib.violation(name, node.location, 'Instance.new("' .. value .. '")', "NotCreatable class errors at runtime", sourcepath)
				)
			end
		end
		local method, mf = lib.methodCall(node)
		if method == "Clone" then
			local recv = lib.chainText(mf.expression)
			if recv and archivableOff[recv] then
				table.insert(
					out,
					lib.violation(name, node.location, recv .. ":Clone()", "returns nil with Archivable = false", sourcepath)
				)
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
