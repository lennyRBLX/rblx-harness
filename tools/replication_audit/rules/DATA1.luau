-- DATA1: a service touches only its same-named subtree. PlayerData:Get reads
-- the 2nd arg, :AddSetup the first field of errorId; the owner is
-- script.Name or the path-derived service name. A guarantee for script.Name
-- and literals, a lean for a computed name.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "DATA1"

local function lint(ast, sourcepath, context)
	local owner = lib.serviceOwner(sourcepath)
	if owner == nil or owner == "PlayerData" then
		return {}
	end
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		-- Typed.<K>(player): the generated accessor's member name is the
		-- statically checkable form of script.Name — a guarantee, same grade
		-- as a literal owner arg
		local f0 = node.func
		if f0.tag == "indexname" and f0.accessor.text == "." then
			local recvChain = lib.chainText(f0.expression)
			if recvChain ~= nil and (recvChain == "Typed" or recvChain:match("%.Typed$")) and f0.index.text ~= owner then
				table.insert(
					out,
					lib.violation(name, node.location, "Typed." .. f0.index.text, "Use Typed." .. owner .. "; retry.", sourcepath)
				)
				return true
			end
		end
		local method, f = lib.methodCall(node)
		local recv = f and lib.chainText(f.expression)
		if recv ~= "PlayerData" then
			return true
		end
		local args = lib.nodes(node.arguments)
		if method == "Get" then
			local ownerArg = args[2]
			if ownerArg == nil then
				table.insert(
					out,
					lib.violation(name, node.location, "PlayerData:Get without owner", "Pass script.Name to PlayerData:Get; retry.", sourcepath)
				)
			elseif lib.chainText(ownerArg) == "script.Name" then
				-- self-correct: a service cannot name another's key this way
			else
				local literal = lib.stringValue(ownerArg)
				if literal ~= nil and literal ~= owner then
					table.insert(
						out,
						lib.violation(name, ownerArg.location, '"' .. literal .. '"', "Move the read behind its owner Service; retry.", sourcepath)
					)
				elseif literal == nil then
					table.insert(
						out,
						lib.violation(name, ownerArg.location, "computed owner arg", "Use script.Name; retry.", sourcepath)
					)
				end
			end
		elseif method == "AddSetup" then
			local errorId = args[3]
			local literal = errorId and lib.stringValue(errorId)
			if literal ~= nil then
				local first = literal:match("^([^.]+)%.")
				if first ~= nil and first ~= owner then
					table.insert(
						out,
						lib.violation(name, errorId.location, '"' .. literal .. '"', "Set the 1st errorId field to " .. owner .. "; retry.", sourcepath)
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
