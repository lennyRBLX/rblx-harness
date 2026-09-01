-- DEBUG8: the traceable pipe format — warns read 'name | player | detail',
-- API named Script.method. Guarantee on the pipe-format shape; whether player
-- and detail are meaningful stays a lean.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "DEBUG8"

local function headLiteral(node)
	-- the leftmost string literal of a concat chain, or the literal itself
	if node.tag == "string" then
		return node
	elseif node.tag == "binary" and node.operator.text == ".." then
		return headLiteral(node.lhsOperand)
	end
	return nil
end

local function chainHasPipes(node)
	if node.tag == "string" then
		return (lib.stringValue(node) or ""):find(" | ", 1, true) ~= nil
	elseif node.tag == "binary" and node.operator.text == ".." then
		return chainHasPipes(node.lhsOperand) or chainHasPipes(node.rhsOperand)
	end
	return false
end

local function lint(ast, sourcepath, context)
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		if lib.globalCall(node) == "warn" then
			local args = lib.nodes(node.arguments)
			local first = args[1]
			if first ~= nil then
				local head = headLiteral(first)
				if head ~= nil and not chainHasPipes(first) then
					table.insert(
						out,
						lib.violation(name, first.location, "warn without pipe format", "'name | player | detail'", sourcepath)
					)
				end
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
