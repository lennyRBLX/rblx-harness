-- OPT19: RaycastParams and ignore lists build once, update on events — a
-- constructor call inside a detected per-frame body is the violation.
local visitor = require("@std/syntax/visitor")
local lib = require("../../replication_audit/lib")
local perframe = require("../perframe")

local name = "OPT19"

local function lint(ast, sourcepath, context)
	local out = {}
	for _, body in perframe.bodies(ast) do
		local v = visitor.create()
		v.visitExprCall = function(node)
			local f = node.func
			if f.tag == "indexname" and f.index.text == "new" and f.expression.tag == "global" and f.expression.name.text == "RaycastParams" then
				table.insert(
					out,
					lib.violation(name, node.location, "RaycastParams built per frame", "hoist to a module-level constant, update on events", sourcepath)
				)
			end
			return true
		end
		visitor.visitBlock(body, v)
	end
	return out
end

return table.freeze({ name = name, lint = lint })
