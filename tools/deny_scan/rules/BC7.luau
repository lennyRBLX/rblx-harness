-- BC7: LocalPlayer is nil on the server. The match is the index name, not the
-- head, so Players.LocalPlayer, game.Players.LocalPlayer and
-- game:GetService("Players").LocalPlayer are one case. A lean — a table field
-- of the same name is indistinguishable from the property in the CST.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "BC7"

local function lint(ast, sourcepath, context)
	local entry = context.options or {}
	local paths = entry.paths or { "ServerScriptService/", "ServerStorage/", ".server.luau", ".server.lua" }
	if not lib.inPaths(sourcepath, paths) then
		return {}
	end
	local patterns = entry.pattern or { "LocalPlayer" }
	local remedy = entry.message or "nil on the server"
	local out = {}
	local v = visitor.create()
	v.visitExprIndexName = function(node)
		if lib.inList(node.index.text, patterns) then
			table.insert(out, lib.violation(name, node.location, node.index.text, remedy, sourcepath))
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
