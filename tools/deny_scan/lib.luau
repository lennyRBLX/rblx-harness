-- shared helpers for the deny_scan lint rules. Rules read the CST, never raw
-- bytes — a denied name in a comment is token trivia and one in a string is a
-- CstExprConstantString value, and neither is a name node.
local path = require("@std/path")

local lib = {}

function lib.pathString(sourcepath)
	if sourcepath == nil then
		return ""
	end
	return (path.format(sourcepath):gsub("\\", "/"))
end

function lib.inPaths(sourcepath, paths)
	if paths == nil or #paths == 0 then
		return true
	end
	local p = lib.pathString(sourcepath)
	for _, needle in paths do
		if p:find(needle, 1, true) then
			return true
		end
	end
	return false
end

function lib.inList(value, list)
	if list == nil then
		return false
	end
	for _, v in list do
		if v == value then
			return true
		end
	end
	return false
end

function lib.violation(name, location, subject, remedy, sourcepath)
	return {
		lintname = name,
		location = location,
		message = subject .. "|" .. remedy,
		severity = "warning",
		sourcepath = sourcepath,
	}
end

function lib.stringValue(node)
	-- token.text on a string constant is the CONTENT, quotes excluded —
	-- measured; a sub(2, -2) here chops real characters
	if node == nil or node.tag ~= "string" then
		return nil
	end
	return node.token.text
end

return lib
