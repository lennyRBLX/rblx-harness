-- shared helpers for replication_audit and perf_audit rules
local path = require("@std/path")
local visitor = require("@std/syntax/visitor")

local lib = {}

function lib.pathString(sourcepath)
	if sourcepath == nil then
		return ""
	end
	return (path.format(sourcepath):gsub("\\", "/"))
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
	if node == nil or node.tag ~= "string" then
		return nil
	end
	return node.token.text
end

function lib.nodes(punctuated)
	local out = {}
	for _, pair in punctuated or {} do
		table.insert(out, pair.node)
	end
	return out
end

function lib.methodCall(callNode)
	if callNode.tag ~= "call" then
		return nil
	end
	local f = callNode.func
	if f.tag == "indexname" and f.accessor.text == ":" then
		return f.index.text, f
	end
	return nil
end

function lib.globalCall(callNode)
	if callNode.tag ~= "call" then
		return nil
	end
	local f = callNode.func
	if f.tag == "global" then
		return f.name.text
	end
	return nil
end

function lib.chainText(node)
	if node == nil then
		return nil
	end
	if node.tag == "global" then
		return node.name.text
	elseif node.tag == "local" then
		return node.token.text
	elseif node.tag == "indexname" then
		local head = lib.chainText(node.expression)
		if head == nil then
			return nil
		end
		return head .. node.accessor.text .. node.index.text
	elseif node.tag == "call" then
		return lib.chainText(node.func)
	end
	return nil
end

-- the service that owns this file, derived from Services/<Name>/ or
-- Services/<Name>.lua[u]; nil outside a service tree
function lib.serviceOwner(sourcepath)
	local p = lib.pathString(sourcepath)
	local owner = p:match("/Services/([^/]+)/") or p:match("/Services/([^/]+)%.luau$") or p:match("/Services/([^/]+)%.lua$")
	return owner
end

-- locals bound from a require whose argument chain contains `needle`, and
-- locals bound from game:GetService("<literal>") — the normal form binds the
-- indirection to a local, so checks resolve the binding instead of matching a
-- member name on any receiver
function lib.resolveBindings(ast)
	local requires = {} -- AstLocal -> chain text of the required module
	local services = {} -- AstLocal -> service name literal
	local v = visitor.create()
	v.visitStatLocalDeclaration = function(node)
		for i, pair in node.variables do
			local valuePair = node.values[i]
			local value = valuePair and valuePair.node
			if value ~= nil and value.tag == "call" then
				local gname = lib.globalCall(value)
				if gname == "require" then
					local arg = lib.nodes(value.arguments)[1]
					local chain = arg and lib.chainText(arg)
					if chain ~= nil then
						requires[pair.node] = chain
					end
				else
					local method, f = lib.methodCall(value)
					if method == "GetService" and f.expression.tag == "global" and f.expression.name.text == "game" then
						local sname = lib.stringValue(lib.nodes(value.arguments)[1])
						if sname ~= nil then
							services[pair.node] = sname
						end
					end
				end
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return requires, services
end

-- module-level locals (top block declarations): AstLocal -> init node
function lib.moduleLocals(ast)
	local out = {}
	for _, stat in ast.statements do
		if stat.tag == "local" then
			for i, pair in stat.variables do
				local valuePair = stat.values[i]
				out[pair.node] = valuePair and valuePair.node or false
			end
		end
	end
	return out
end

return lib
