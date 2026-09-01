-- WRIT19: constants use UPPER_SNAKE_CASE. Module-level variables use
-- PascalCase, excluding m. A module-level local is a constant only when the
-- initializer is a scalar literal and the name is never rebound. Blocks
-- rather than repairs: a formatter cannot safely rename.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT19"

local SCALAR = { string = true, number = true, boolean = true, ["nil"] = true }

local function isUpperSnake(text)
	return text:match("^[A-Z][A-Z0-9_]*$") ~= nil and not text:find("__", 1, true) and not text:match("_$")
end

local function isPascal(text)
	return text:match("^[A-Z][A-Za-z0-9]*$") ~= nil and (#text == 1 or text:match("%l") ~= nil)
end

local function lint(ast, sourcepath, context)
	local out = {}
	local rebound = {}
	local v = visitor.create()
	v.visitStatAssign = function(node)
		for _, pair in node.variables do
			if pair.node.tag == "local" then
				rebound[pair.node["local"]] = true
			end
		end
		return true
	end
	v.visitStatCompoundAssign = function(node)
		if node.variable.tag == "local" then
			rebound[node.variable["local"]] = true
		end
		return true
	end
	visitor.visitBlock(ast, v)

	for _, stat in ast.statements do
		if stat.tag == "local" then
			for i, pair in stat.variables do
				local decl = pair.node
				local bindingName = decl.name.text
				local valuePair = stat.values[i]
				local value = valuePair and valuePair.node
				local isConstant =
					value ~= nil
					and SCALAR[value.tag]
					and not rebound[decl]

				if bindingName ~= "m" and isConstant and not isUpperSnake(bindingName) then
					table.insert(
						out,
						lib.violation(name, decl.location, bindingName, "constants use UPPER_SNAKE_CASE", sourcepath)
					)
				elseif bindingName ~= "m" and not isConstant and not isPascal(bindingName) then
					table.insert(
						out,
						lib.violation(name, decl.location, bindingName, "module-level variables use PascalCase", sourcepath)
					)
				end
			end
		end
	end
	return out
end

return table.freeze({ name = name, lint = lint })
