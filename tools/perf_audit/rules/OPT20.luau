-- OPT20: standing profile labels — per-frame loops ship debug.profilebegin
-- with a literal 'Module.function.Sum' label, one open, and every exit
-- (return/break/fall-through) preceded by debug.profileend().
local visitor = require("@std/syntax/visitor")
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
	local out = {}
	for _, body in perframe.bodies(ast) do
		local stats = body.statements
		local beginCall = nil
		for _, stat in stats do
			local c = debugCall(stat, "profilebegin")
			if c ~= nil then
				if beginCall ~= nil then
					table.insert(out, lib.violation(name, c.location, "second profilebegin", "one open per per-frame body", sourcepath))
				end
				beginCall = c
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
		-- every exit closes: each return/break, and the fall-through end,
		-- preceded by debug.profileend()
		local function checkBlock(block)
			for i, stat in block.statements do
				if stat.tag == "return" or stat.tag == "break" then
					local prev = block.statements[i - 1]
					if prev == nil or debugCall(prev, "profileend") == nil then
						table.insert(
							out,
							lib.violation(name, stat.location, "exit without profileend", "every exit closes the label", sourcepath)
						)
					end
				end
			end
		end
		local v = visitor.create()
		v.visitStatBlock = function(block)
			checkBlock(block)
			return true
		end
		visitor.visitBlock(body, v)
		local last = stats[#stats]
		if last ~= nil and last.tag ~= "return" and debugCall(last, "profileend") == nil then
			table.insert(
				out,
				lib.violation(name, last.location, "fall-through without profileend", "every exit closes the label", sourcepath)
			)
		end
	end
	return out
end

return table.freeze({ name = name, lint = lint })
