-- DES5: release-gate on ReleaseDate; delete the guard once the date passed.
-- The Update -> ReleaseDate map comes through context.globals (session-gate
-- emits it); the comparison date is pinned through context.options in
-- fixtures and os.time() in production.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "DES5"

local function parseDate(s)
	local y, m, d = s:match("^(%d%d%d%d)-(%d%d)-(%d%d)$")
	if y == nil then
		return nil
	end
	return os.time({ year = tonumber(y) :: number, month = tonumber(m) :: number, day = tonumber(d) :: number, hour = 23, min = 59, sec = 59 })
end

local function lint(ast, sourcepath, context)
	local options = context.options or {}
	local now = tonumber(options.now) or os.time()
	local updates = (context.globals or {}).updates or {}

	local out = {}
	local v = visitor.create()
	v.visitStatIf = function(node)
		local touchesRelease = false
		local literalDate = nil
		local cv = visitor.create()
		cv.visitExprIndexName = function(n)
			if n.index.text == "ReleaseDate" then
				touchesRelease = true
			end
			return true
		end
		cv.visitExprGlobal = function(n)
			if n.name.text == "ReleaseDate" then
				touchesRelease = true
			end
			return true
		end
		cv.visitExprLocal = function(n)
			if n.token.text == "ReleaseDate" then
				touchesRelease = true
			end
			return true
		end
		cv.visitExprConstantString = function(n)
			local when = parseDate(lib.stringValue(n) or "")
			if when ~= nil then
				literalDate = when
			end
			return true
		end
		visitor.visitExpression(node.condition, cv)
		if touchesRelease then
			local when = literalDate
			if when == nil then
				local p = lib.pathString(sourcepath)
				local stem = p:match("([^/]+)%.luau$") or p:match("([^/]+)%.lua$")
				if stem and updates[stem] then
					when = parseDate(updates[stem])
				end
			end
			if when ~= nil and now > when then
				table.insert(
					out,
					lib.violation(name, node.location, "ReleaseDate guard, date passed", "delete the guard - the release shipped", sourcepath)
				)
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
