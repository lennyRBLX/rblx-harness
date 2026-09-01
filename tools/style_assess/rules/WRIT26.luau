-- WRIT26 (placement clause): update modules ship the contract — permanent
-- content above the notLatestUpdate return, temporary below and cleaned up in
-- :Destroy. Checks only Updates/*.lua[u] that are not init.lua[u]. The
-- "obtainable after rotation" half is reviewer judgment no lint can see.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT26"

local function lint(ast, sourcepath, context)
	local p = lib.pathString(sourcepath)
	if not p:find("/Updates/", 1, true) or p:find("init%.luau$") or p:find("init%.lua$") then
		return {}
	end
	local sawGate, gateLine = false, 0
	local sawDestroy = false
	local v = visitor.create()
	v.visitExprIndexName = function(node)
		if node.index.text == "notLatestUpdate" then
			sawGate = true
			gateLine = math.max(gateLine, node.location.beginLine)
		elseif node.index.text == "Destroy" then
			sawDestroy = true
		end
		return true
	end
	v.visitExprGlobal = function(node)
		if node.name.text == "notLatestUpdate" then
			sawGate = true
			gateLine = math.max(gateLine, node.location.beginLine)
		end
		return true
	end
	v.visitExprLocal = function(node)
		if node.token.text == "notLatestUpdate" then
			sawGate = true
			gateLine = math.max(gateLine, node.location.beginLine)
		end
		return true
	end
	v.visitStatFunction = function(node)
		local fname = node.name
		if fname.tag == "indexname" and fname.index.text == "Destroy" then
			sawDestroy = true
		end
		return true
	end
	visitor.visitBlock(ast, v)
	if not sawGate then
		return {
			lib.violation(name, lib.at(1, 1), "no notLatestUpdate gate", "perm content above the notLatestUpdate return, temp below", sourcepath),
		}
	end
	if not sawDestroy then
		return {
			lib.violation(name, lib.at(gateLine, 1), "temp content with no :Destroy cleanup", "clean temp content up in :Destroy", sourcepath),
		}
	end
	return {}
end

return table.freeze({ name = name, lint = lint })
