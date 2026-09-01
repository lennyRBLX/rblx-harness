-- DATA17: profiles use ProfileStore:VersionQuery; the DataStore version APIs
-- belong to raw DataStores. A DataStore version method on a resolved
-- ProfileStore binding is the violation.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "DATA17"

local DS_VERSION = { ListVersionsAsync = true, GetVersionAsync = true, GetVersionAtTimeAsync = true }

local function lint(ast, sourcepath, context)
	local requires = lib.resolveBindings(ast)
	local profileNames = { PlayerData = true }
	for decl, chain in requires do
		if chain:find("ProfileStore", 1, true) or chain:find("PlayerData", 1, true) then
			profileNames[decl.name.text] = true
		end
	end
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local method, f = lib.methodCall(node)
		if method ~= nil and DS_VERSION[method] then
			local chain = lib.chainText(f.expression)
			local root = chain and chain:match("^([%w_]+)")
			if root ~= nil and profileNames[root] then
				table.insert(
					out,
					lib.violation(name, node.location, chain .. ":" .. method, "Use ProfileStore:VersionQuery; retry.", sourcepath)
				)
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
