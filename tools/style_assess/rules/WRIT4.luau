-- WRIT4: attribute names, tags, remote names, Exclusive/replication keys are
-- hoisted top-of-file constants — a bare string literal at one of those call
-- sites should be a constant. The Exclusive key constant is named INFO_NAME.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT4"

local KEY_METHODS = {
	GetAttribute = true,
	SetAttribute = true,
	GetAttributeChangedSignal = true,
	AddTag = true,
	RemoveTag = true,
	HasTag = true,
	GetTagged = true,
	Set = true, -- Exclusive:Set(player, INFO_NAME, ...)
	Get = true,
}

local function lint(ast, sourcepath, context)
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local method, f = lib.methodCall(node)
		if method ~= nil and KEY_METHODS[method] then
			-- Set/Get are Exclusive's replication-key methods; on any other
			-- receiver they are ordinary accessors (PlayerData:Get's literal
			-- is DATA1's domain, not a hoistable key)
			if method == "Set" or method == "Get" then
				local recv = lib.chainText(f.expression)
				if recv == nil or not (recv == "Exclusive" or recv:match("Exclusive$")) then
					return true
				end
			end
			for _, arg in lib.nodes(node.arguments) do
				local value = lib.stringValue(arg)
				if value ~= nil and value ~= "" then
					table.insert(
						out,
						lib.violation(
							name,
							arg.location,
							method .. ' "' .. value .. '"',
							"hoist the key to a top-of-file constant",
							sourcepath
						)
					)
					break -- one finding per call site
				end
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
