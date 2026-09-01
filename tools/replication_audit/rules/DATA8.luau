-- DATA8: migration callbacks are pcall-wrapped centrally by PlayerData; what
-- project code owns is the traceable errorId — 'Service.migration' — and any
-- warn inside the callback matching 'Service.migration | player | detail'.
-- Guarantee on the literal errorId shape; lean on a named function defined
-- elsewhere.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "DATA8"

local function lint(ast, sourcepath, context)
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local method, f = lib.methodCall(node)
		if method ~= "AddSetup" then
			return true
		end
		local recv = f and lib.chainText(f.expression)
		if recv ~= "PlayerData" then
			return true
		end
		local args = lib.nodes(node.arguments)
		local errorId = args[3]
		if errorId == nil then
			table.insert(
				out,
				lib.violation(name, node.location, "AddSetup without errorId", "Add literal errorId 'Service.migration'; retry.", sourcepath)
			)
			return true
		end
		local literal = lib.stringValue(errorId)
		if literal == nil then
			table.insert(
				out,
				lib.violation(name, errorId.location, "computed errorId", "Use literal errorId 'Service.migration'; retry.", sourcepath)
			)
		elseif not literal:match("^[%w_]+%.[%w_]+$") then
			table.insert(
				out,
				lib.violation(name, errorId.location, '"' .. literal .. '"', "Use 'Service.migration'; retry.", sourcepath)
			)
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
