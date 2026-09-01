-- OPT18: per-frame CFrame writes batch into one workspace:BulkMoveTo;
-- buffers table.clear, never realloc. Guarantee on table.clear versus
-- realloc; lean on batching — whether N writes should have been one
-- BulkMoveTo is not statically decidable.
local visitor = require("@std/syntax/visitor")
local lib = require("../../replication_audit/lib")
local perframe = require("../perframe")

local name = "OPT18"

local function lint(ast, sourcepath, context)
	local out = {}
	local moduleLocals = lib.moduleLocals(ast)
	for _, body in perframe.bodies(ast) do
		local cframeWrites = {}
		local v = visitor.create()
		v.visitStatAssign = function(stat)
			for i, pair in stat.variables do
				local t = pair.node
				if t.tag == "indexname" and t.index.text == "CFrame" then
					table.insert(cframeWrites, t.location)
				end
				-- buffer realloc: a module-level local reassigned to {} per frame
				if t.tag == "local" and moduleLocals[t["local"]] ~= nil then
					local valuePair = stat.values[i]
					if valuePair and valuePair.node.tag == "table" and #valuePair.node.entries == 0 then
						table.insert(
							out,
							lib.violation(name, t.location, t.token.text .. " = {} per frame", "table.clear, never realloc", sourcepath)
						)
					end
				end
			end
			return true
		end
		v.visitStatFor = function(stat)
			return true
		end
		visitor.visitBlock(body, v)
		if #cframeWrites >= 2 then
			table.insert(
				out,
				lib.violation(name, cframeWrites[1], #cframeWrites .. " per-frame CFrame writes", "batch into one workspace:BulkMoveTo", sourcepath)
			)
		end
	end
	return out
end

return table.freeze({ name = name, lint = lint })
