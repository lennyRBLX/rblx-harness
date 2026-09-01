-- WRIT29: pcall on a Yields/Throws member; xpcall + debug.traceback on a
-- runtime-resolved target; CanYield (WaitForChild) takes a timeout and a
-- nil-check, never a guard. Member sets come from api_dump through
-- context.globals. A lean: the receiver's class is unknowable from the CST,
-- so matching is by member name.
local syntax = require("@std/syntax")
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT29"

local function memberSet(map)
	local out = {}
	for key in map or {} do
		local member = key:match("[:.]([%w_]+)$")
		if member then
			out[member] = true
		end
	end
	return out
end

local function lint(ast, sourcepath, context)
	local globals = context.globals or {}
	if globals.yields == nil and globals.throws == nil then
		return {}
	end
	local guarded = memberSet(globals.yields)
	for member in memberSet(globals.throws) do
		guarded[member] = true
	end
	-- excepted members: a throw made impossible by another gate (WRIT25
	-- validates GetService names) or a nil-contract OPT12 already owns
	for _, member in (context.options or {}).except or {} do
		guarded[member] = nil
	end
	local canyield = memberSet(globals.canyield)

	local out = {}
	local pcallSpans = {}

	local v = visitor.create()
	v.visitExprCall = function(node)
		local gname = lib.globalCall(node)
		if gname == "pcall" or gname == "xpcall" then
			table.insert(pcallSpans, node.location)
		end
		return true
	end
	visitor.visitBlock(ast, v)

	local function wrapped(location)
		for _, span in pcallSpans do
			if syntax.span.subsumes(location, span) then
				return true
			end
		end
		return false
	end

	local v2 = visitor.create()
	v2.visitExprCall = function(node)
		local method = lib.methodCall(node)
		if method == nil then
			return true
		end
		if canyield[method] then
			-- CanYield takes a timeout and a nil-check, never a guard
			local args = lib.nodes(node.arguments)
			if #args < 2 then
				table.insert(
					out,
					lib.violation(name, node.location, method .. " without timeout", "pass a timeout and nil-check the result", sourcepath)
				)
			elseif wrapped(node.location) then
				table.insert(
					out,
					lib.violation(name, node.location, method .. " guarded", "CanYield takes a timeout and a nil-check, never a guard", sourcepath)
				)
			end
		elseif guarded[method] and not wrapped(node.location) then
			table.insert(
				out,
				lib.violation(name, node.location, method, "pcall a Yields/Throws member", sourcepath)
			)
		end
		return true
	end
	visitor.visitBlock(ast, v2)
	return out
end

return table.freeze({ name = name, lint = lint })
