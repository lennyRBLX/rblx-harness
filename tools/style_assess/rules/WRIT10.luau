-- WRIT10: module names are bare feature nouns — never XService / XController.
local lib = require("../stylelib")

local name = "WRIT10"

local function lint(ast, sourcepath, context)
	local p = lib.pathString(sourcepath)
	if not (p:find("/Services/", 1, true) or p:find("/Controllers/", 1, true)) then
		return {}
	end
	local stem = p:match("([^/]+)%.luau$") or p:match("([^/]+)%.lua$") or ""
	if stem == "init" then
		stem = p:match("([^/]+)/init%.luau$") or p:match("([^/]+)/init%.lua$") or stem
	end
	if stem:find("Service", 1, true) or stem:find("Controller", 1, true) then
		local bare = stem:gsub("Service", ""):gsub("Controller", "")
		return {
			lib.violation(name, lib.at(1, 1), stem, "name after the feature: " .. bare, sourcepath),
		}
	end
	return {}
end

return table.freeze({ name = name, lint = lint })
