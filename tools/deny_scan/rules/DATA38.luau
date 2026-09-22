-- DATA38: literal codec mistakes. Computed bounds/schema need boundary review.
local visitor = require("@std/syntax/visitor")
local lib = require("../../style_assess/stylelib")
local name = "DATA38"

local function numberLiteral(node)
	if node == nil then return nil end
	if node.tag == "number" then
		return tonumber((node.token.text:gsub("_", "")))
	elseif node.tag == "unary" and node.operator.text == "-" then
		local n = numberLiteral(node.operand)
		return if n then -n else nil
	end
	return nil
end

local function lint(ast, sourcepath, context)
	local out = {}
	local function note(node, subject, remedy)
		table.insert(out, lib.violation(name, node.location, subject, remedy, sourcepath))
	end
	local v = visitor.create()
	v.visitExprCall = function(node)
		local f = node.func
		if f.tag ~= "indexname" or f.expression.tag ~= "global" or f.expression.name.text ~= "buffer" then
			return true
		end
		local args = lib.nodes(node.arguments)
		local value = args[3]
		local member = f.index.text
		if member:match("^write[ui]%d+$") or member == "writef32" then
			if value and value.tag == "indexname" and value.index.text == "UserId" then
				note(value, "lossy UserId encoding", "use f64 or a lossless string/ID mapping")
			end
		end
		local signed, bits = member:match("^write([ui])(%d+)$")
		if signed and value then
			local n = numberLiteral(value)
			local width = tonumber(bits)
			if width and (width == 8 or width == 16 or width == 32) and n then
				local low = if signed == "i" then -(2 ^ (width - 1)) else 0
				local high = if signed == "i" then 2 ^ (width - 1) - 1 else 2 ^ width - 1
				if n < low or n > high or n % 1 ~= 0 then
					note(value, "integer codec truncates literal", "validate range and integrality before encoding")
				end
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
