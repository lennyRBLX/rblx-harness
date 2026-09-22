-- OPT20: standing profile labels — per-frame loops ship debug.profilebegin
-- with a literal 'Module.function.Sum' label, nested profiles allowed; flow checks every exit.
local flow = require("../flow")
local lib = require("../../replication_audit/lib")
local perframe = require("../perframe")

local name = "OPT20"

local function debugCall(stat, member)
	if stat.tag ~= "expression" or stat.expression.tag ~= "call" then
		return nil
	end
	local f = stat.expression.func
	if f.tag == "indexname" and f.expression.tag == "global" and f.expression.name.text == "debug" and f.index.text == member then
		return stat.expression
	end
	return nil
end

local function lint(ast, sourcepath, context)
	local out = flow.lint(ast, sourcepath, "profile", false)
	for _, body in perframe.bodies(ast) do
		local stats = body.statements
		local beginCall = nil
		for _, stat in stats do
			local c = debugCall(stat, "profilebegin")
			if c ~= nil then
				beginCall = beginCall or c
			end
		end
		if beginCall == nil then
			table.insert(
				out,
				lib.violation(name, body.location, "per-frame body without standing label", "debug.profilebegin 'Module.function.Sum'", sourcepath)
			)
			continue
		end
		local label = lib.stringValue(lib.nodes(beginCall.arguments)[1])
		if label == nil or not label:match("^[%w_]+%.[%w_]+") then
			table.insert(
				out,
				lib.violation(name, beginCall.location, tostring(label), "label format is Module.function.Sum", sourcepath)
			)
		end
	end
	return out
end

return table.freeze({ name = name, lint = lint })
