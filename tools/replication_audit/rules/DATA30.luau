-- DATA30: only PlayerData touches ProfileStore — a resolved ProfileStore
-- binding outside PlayerData/ is the violation, and it holds through any
-- alias because the require chain is what resolves.
local lib = require("../lib")

local name = "DATA30"

local function lint(ast, sourcepath, context)
	local p = lib.pathString(sourcepath)
	if p:match("/Services/PlayerData/") or p:match("/Services/PlayerData%.luau$") or p:match("/Services/PlayerData%.lua$") or p:match("/Modules/") then
		return {}
	end
	local requires = lib.resolveBindings(ast)
	local out = {}
	for decl, chain in requires do
		if chain:find("ProfileStore", 1, true) or chain:find("ProfileService", 1, true) then
			table.insert(
				out,
				lib.violation(name, decl.location, "require " .. chain, "Move ProfileStore access into PlayerData; retry.", sourcepath)
			)
		end
	end
	return out
end

return table.freeze({ name = name, lint = lint })
