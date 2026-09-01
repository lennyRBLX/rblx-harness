-- OPT17: Trove:AttachToInstance never takes a workspace descendant — the
-- attachment dies on stream-out.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "OPT17"

local function lint(ast, sourcepath, context)
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local method = lib.methodCall(node)
		if method == "AttachToInstance" then
			for _, arg in lib.nodes(node.arguments) do
				local chain = lib.chainText(arg)
				if chain ~= nil and chain:match("^workspace[.:]") then
					table.insert(
						out,
						lib.violation(name, arg.location, chain, "never a workspace descendant - it dies on stream-out", sourcepath)
					)
				end
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
