-- WRIT32: a client script that reads LocalPlayer binds it once to Player at
-- top of script, and reads Player thereafter. The match is the index name,
-- not the head, so Players.LocalPlayer, game.Players.LocalPlayer and
-- game:GetService("Players").LocalPlayer are one case. A lean — a table field
-- of the same name is indistinguishable from the property in the CST. Says
-- nothing about the server tree, which it skips; BC7 owns that.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT32"

local SERVER_PATHS = { "ServerScriptService/", "ServerStorage/", ".server.luau", ".server.lua" }

local function lint(ast, sourcepath, context)
	if lib.inPaths(sourcepath, SERVER_PATHS) then
		return {}
	end
	local bound = {}
	local out = {}

	-- pass 1: the bindings — their name, and whether they sit at top of script
	local v = visitor.create()
	local depth = 0
	v.visitExprFunction = function()
		depth += 1
		return true
	end
	v.visitExprFunctionEnd = function()
		depth -= 1
	end
	v.visitStatBlock = function(block)
		for _, stat in block.statements do
			if stat.tag == "local" and #stat.variables == 1 then
				local valuePair = stat.values[1]
				local value = valuePair and valuePair.node
				if value ~= nil and value.tag == "indexname" and value.index.text == "LocalPlayer" then
					bound[value] = true
					local varName = stat.variables[1].node.name.text
					if varName ~= "Player" then
						table.insert(
							out,
							lib.violation(name, stat.location, "local " .. varName, "the LocalPlayer binding is named Player", sourcepath)
						)
					elseif depth > 0 then
						table.insert(
							out,
							lib.violation(name, stat.location, "local Player inside a function", "bind it once at top of script", sourcepath)
						)
					end
				end
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)

	-- pass 2: every other read. Separate walk because a binding in a block
	-- visited later must still sanction a read the first walk already passed.
	local v2 = visitor.create()
	v2.visitExprIndexName = function(node)
		if node.index.text == "LocalPlayer" and not bound[node] then
			table.insert(
				out,
				lib.violation(
					name,
					node.location,
					lib.chainText(node) or "LocalPlayer",
					"bind it once at top of script: local Player = Players.LocalPlayer",
					sourcepath
				)
			)
		end
		return true
	end
	visitor.visitBlock(ast, v2)
	return out
end

return table.freeze({ name = name, lint = lint })
