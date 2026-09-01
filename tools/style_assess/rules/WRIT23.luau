-- WRIT23: datatype arithmetic — the operator matrix comes from api_dump
-- through context.globals, never hardcoded. A lean: operand types resolve
-- only through <Datatype>.new(...) constructors and locals initialized from
-- them.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT23"

local OPS = { ["+"] = true, ["-"] = true, ["*"] = true, ["/"] = true, ["//"] = true }

local function lint(ast, sourcepath, context)
	local ops = (context.globals or {}).ops
	if ops == nil or #ops == 0 then
		return {}
	end
	local legal = {}
	local knownType = {}
	for _, row in ops do
		legal[row.op .. "|" .. row.a .. "|" .. row.b] = row.ret
		knownType[row.a], knownType[row.b] = true, true
	end
	knownType["number"] = true

	local localType = {}

	local function typeOf(node)
		if node.tag == "number" then
			return "number"
		elseif node.tag == "call" then
			local f = node.func
			if f.tag == "indexname" and f.index.text == "new" and f.expression.tag == "global" then
				local dt = f.expression.name.text
				if knownType[dt] then
					return dt
				end
			end
		elseif node.tag == "local" then
			return localType[node["local"]]
		elseif node.tag == "group" then
			return typeOf(node.expression)
		end
		return nil
	end

	local out = {}
	local v = visitor.create()
	v.visitStatLocalDeclaration = function(node)
		for i, pair in node.variables do
			local valuePair = node.values[i]
			if valuePair then
				localType[pair.node] = typeOf(valuePair.node)
			end
		end
		return true
	end
	v.visitExprBinary = function(node)
		local op = node.operator.text
		if OPS[op] then
			local a, b = typeOf(node.lhsOperand), typeOf(node.rhsOperand)
			if a ~= nil and b ~= nil and not (a == "number" and b == "number") then
				if legal[op .. "|" .. a .. "|" .. b] == nil then
					table.insert(
						out,
						lib.violation(
							name,
							node.location,
							a .. " " .. op .. " " .. b,
							"not in the datatype operator matrix",
							sourcepath
						)
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
