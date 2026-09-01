-- DATA29: Studio runs against .Mock — a presence rule. PlayerData/init.luau
-- must branch RunService:IsStudio() to the .Mock store; the violation is the
-- ABSENCE of that branch, reported at 1,1.
local syntax = require("@std/syntax")
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "DATA29"

local function lint(ast, sourcepath, context)
	local entry = context.options or {}
	local paths = entry.paths or { "Services/PlayerData/" }
	if #paths > 0 then
		local p = lib.pathString(sourcepath)
		local hit = false
		for _, needle in paths do
			if p:find(needle, 1, true) then
				hit = true
				break
			end
		end
		if not hit then
			return {}
		end
	end
	local sawIsStudio, sawMock = false, false
	local v = visitor.create()
	v.visitExprIndexName = function(node)
		if node.index.text == "IsStudio" then
			sawIsStudio = true
		elseif node.index.text == "Mock" then
			sawMock = true
		end
		return true
	end
	visitor.visitBlock(ast, v)
	if sawIsStudio and sawMock then
		return {}
	end
	local loc = syntax.span.create({ beginLine = 1, beginColumn = 1, endLine = 1, endColumn = 1 })
	return {
		lib.violation(
			name,
			loc,
			"RunService:IsStudio() -> .Mock branch absent",
			entry.message or "data does not save in Studio; branch to .Mock",
			sourcepath
		),
	}
end

return table.freeze({ name = name, lint = lint })
