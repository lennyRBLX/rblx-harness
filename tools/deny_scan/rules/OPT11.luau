-- OPT11: streaming properties set in Studio, never in code. Property names
-- and tags come from api_dump through context.globals — never hardcoded. With
-- no globals the rule matches nothing; the wrapper prints SKIPPED OPT11, so
-- "0 findings" never silently means "checked everything".
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "OPT11"

local function lint(ast, sourcepath, context)
	local streaming = (context.globals or {}).streaming
	if streaming == nil or next(streaming) == nil then
		return {}
	end
	local entry = context.options or {}
	local remedy = entry.message or "streaming properties set in Studio, never in code"
	local out = {}

	local function check(target)
		if target ~= nil and target.tag == "indexname" and streaming[target.index.text] ~= nil then
			table.insert(
				out,
				lib.violation(name, target.location, target.index.text .. " assigned", remedy, sourcepath)
			)
		end
	end

	local v = visitor.create()
	v.visitStatAssign = function(node)
		for _, pair in node.variables do
			check(pair.node)
		end
		return true
	end
	v.visitStatCompoundAssign = function(node)
		check(node.variable)
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
