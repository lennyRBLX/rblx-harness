-- DES2: Payments wraps all marketplace logic — a marketplace call on a
-- resolved MarketplaceService binding outside Payments is the violation. The
-- binding is resolved (GetService bound to a local), so the check holds
-- through aliasing.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "DES2"

local function lint(ast, sourcepath, context)
	local p = lib.pathString(sourcepath)
	if p:match("/Services/Payments") then
		return {}
	end
	local _, services = lib.resolveBindings(ast)
	local marketLocals = {}
	for decl, sname in services do
		if sname == "MarketplaceService" then
			marketLocals[decl] = true
		end
	end
	if next(marketLocals) == nil then
		return {}
	end
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local method, f = lib.methodCall(node)
		if method == nil then
			return true
		end
		local recv = f.expression
		if recv.tag == "local" and marketLocals[recv["local"]] then
			table.insert(
				out,
				lib.violation(name, node.location, "MarketplaceService:" .. method, "Move the MarketplaceService call into Payments; retry.", sourcepath)
			)
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
