-- OPT15: DataModel writes follow task.synchronize() — a property or attribute
-- assignment, reparent, or mutating method call inside a parallel block with
-- no preceding task.synchronize(); Instance.new exempt. The syntactic block
-- form only — writes reached through a helper are optimizer doctrine.
local visitor = require("@std/syntax/visitor")
local lib = require("../../replication_audit/lib")

local name = "OPT15"

local MUTATING = { SetAttribute = true, Destroy = true, ClearAllChildren = true, AddTag = true, RemoveTag = true, PivotTo = true }

local function taskCallName(stat)
	if stat.tag ~= "expression" or stat.expression.tag ~= "call" then
		return nil
	end
	local f = stat.expression.func
	if f.tag == "indexname" and f.expression.tag == "global" and f.expression.name.text == "task" then
		return f.index.text
	end
	return nil
end

local function isDataModelWrite(stat)
	if stat.tag == "assign" then
		for _, pair in stat.variables do
			local t = pair.node
			if t.tag == "indexname" and t.index.text:match("^%u") then
				return t.location, lib.chainText(t) or t.index.text
			end
		end
	elseif stat.tag == "expression" and stat.expression.tag == "call" then
		local method = lib.methodCall(stat.expression)
		if method ~= nil and MUTATING[method] then
			return stat.expression.location, ":" .. method
		end
	end
	return nil
end

local function lint(ast, sourcepath, context)
	local out = {}
	local v = visitor.create()
	v.visitStatBlock = function(block)
		local parallel = false
		for _, stat in block.statements do
			local tname = taskCallName(stat)
			if tname == "desynchronize" then
				parallel = true
			elseif tname == "synchronize" then
				parallel = false
			elseif parallel then
				local loc, subject = isDataModelWrite(stat)
				if loc ~= nil then
					table.insert(
						out,
						lib.violation(name, loc, subject .. " in parallel block", "task.synchronize() before DataModel writes", sourcepath)
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
