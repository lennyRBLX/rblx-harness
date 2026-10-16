-- WRIT1: name module tables m; return m; use : for methods unless OOP (m.new()).
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT1"

local function lint(ast, sourcepath, context)
	local function unwrap(node)
		while node do
			if node.tag == "group" then
				node = node.expression
			elseif node.tag == "cast" then
				node = node.operand
			elseif node.tag == "call" and lib.chainText(node.func) == "table.freeze"
				and node.func.expression.tag == "global" and #node.arguments == 1 then
				node = node.arguments[1].node
			else
				break
			end
		end
		return node
	end

	local stats = ast.statements
	local last = stats[#stats]
	if not last or last.tag ~= "return" or #last.expressions ~= 1 then
		return {}
	end
	local returned = unwrap(last.expressions[1].node)
	if not returned or returned.tag ~= "local" then
		return {}
	end
	local decl = returned["local"]
	local values = {}
	for _, stat in stats do
		if stat.tag == "local" then
			for i, pair in stat.variables do
				if stat.values[i] then
					values[pair.node] = stat.values[i].node
				end
			end
		elseif stat.tag == "localfunction" then
			values[stat.name] = stat.func
		end
	end
	local moduleTable = unwrap(values[decl])
	if not moduleTable or moduleTable.tag ~= "table" then
		return {}
	end

	local out = {}
	local returnedName = returned.token.text
	if returnedName ~= "m" then
		table.insert(out, lib.violation(name, decl.location, returnedName, "name the module table m", sourcepath))
	end

	local function member(node)
		if node and node.tag == "indexname" then
			local receiver = unwrap(node.expression)
			if receiver.tag == "local" and receiver["local"] == decl then
				return node.index.text
			end
		end
		return nil
	end

	local function isFunction(node)
		node = unwrap(node)
		while node and node.tag == "local" do
			node = unwrap(values[node["local"]])
		end
		return node and node.tag == "function"
	end

	local methods = {}
	local fields = {}
	for _, entry in moduleTable.entries do
		if entry.kind == "record" and isFunction(entry.value) then
			methods[entry.key.text] = true
			table.insert(fields, entry)
		end
	end
	local collect = visitor.create()
	collect.visitStatFunction = function(node)
		local key = member(node.name)
		if key then methods[key] = true end
		return true
	end
	collect.visitStatAssign = function(node)
		for i, pair in node.variables do
			local key = member(pair.node)
			local value = node.values[i]
			if key and value and isFunction(value.node) then
				methods[key] = true
			end
		end
		return true
	end
	visitor.visitBlock(ast, collect)
	if methods.new then
		return out
	end

	local reported = {}
	local function report(node, key)
		if not reported[node] then
			reported[node] = true
			table.insert(out, lib.violation(name, node.location, returnedName .. "." .. key,
				"use : for module methods", sourcepath))
		end
	end
	for _, entry in fields do
		report(entry.value, entry.key.text)
	end
	local check = visitor.create()
	check.visitExprIndexName = function(node)
		local key = member(node)
		if key and node.accessor.text == "." and methods[key] then
			report(node, key)
		end
		return true
	end
	check.visitExprCall = function(node)
		local func = unwrap(node.func)
		local key = member(func)
		if key and func.accessor.text == "." then
			report(func, key)
		end
		return true
	end
	visitor.visitBlock(ast, check)
	return out
end

return table.freeze({ name = name, lint = lint })
