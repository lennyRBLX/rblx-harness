-- Intraprocedural scope checks. Branches retain separate states; loops must
-- restore entry state at backedges. Functions never close their caller's scope.
local visitor = require("@std/syntax/visitor")
local lib = require("../style_assess/stylelib")

local flow = {}

local function truth(node)
	if node and node.tag == "boolean" then return node.value end
	if node and node.tag == "nil" then return false end
	return nil
end

local function clone(s)
	return { depth = s.depth, parallel = s.parallel, owed = s.owed }
end

local function same(a, b)
	return a.depth == b.depth and a.parallel == b.parallel and a.owed == b.owed
end

local function merge(into, states)
	for _, state in states do
		local found = false
		for _, old in into do
			if same(old, state) then found = true break end
		end
		if not found then table.insert(into, state) end
	end
	return into
end

function flow.lint(ast, sourcepath, mode, writes)
	local name = if mode == "profile" then "OPT20" else "OPT15"
	local out, seen = {}, {}
	local function report(node, subject, remedy)
		local loc = node.location
		local key = tostring(loc.beginLine) .. ":" .. tostring(loc.beginColumn) .. subject
		if not seen[key] then
			seen[key] = true
			table.insert(out, lib.violation(name, loc, subject, remedy, sourcepath))
		end
	end
	local function exitScope(node, state)
		if mode == "profile" and state.depth ~= 0 then
			report(node, "exit with open profile", "close every profile on each exit")
		elseif mode == "parallel" and state.owed then
			report(node, "exit after desynchronize", "synchronize before leaving this function")
		end
	end
	local function expression(expr, state)
		if expr == nil then return end
		local v = visitor.create()
		v.visitExprFunction = function() return false end
		v.visitExprCall = function(node)
			local head = lib.chainText(node.func)
			if mode == "profile" then
				if head == "debug.profilebegin" and node.func.expression.tag == "global" then
					state.depth += 1
				elseif head == "debug.profileend" and node.func.expression.tag == "global" then
					if state.depth == 0 then
						report(node, "profileend without profilebegin", "open and close profiles in the same function")
					else state.depth -= 1 end
				end
			elseif head == "task.desynchronize" and node.func.expression.tag == "global" then
				state.parallel, state.owed = true, true
			elseif head == "task.synchronize" and node.func.expression.tag == "global" then
				-- synchronize is idempotent; parallel callbacks need no explicit opener.
				state.parallel, state.owed = false, false
			elseif state.parallel == true then
				if lib.globalCall(node) == "require" then
					report(node, "require in parallel", "require dependencies before desynchronize")
				elseif writes then
					local method = lib.methodCall(node)
					if method == "SetAttribute" or method == "Destroy" or method == "ClearAllChildren"
						or method == "AddTag" or method == "RemoveTag" or method == "PivotTo" then
						report(node, ":" .. method .. " in parallel", "check API thread safety; synchronize before unsafe writes")
					end
				end
			end
			return true
		end
		visitor.visitExpression(expr, v)
	end
	local block
	block = function(body, states)
		local breaks, continues = {}, {}
		for _, stat in body.statements do
			local nextStates = {}
			for _, incoming in states do
				local s = clone(incoming)
				local tag = stat.tag
				if tag == "conditional" then
					local branches = { { condition = stat.condition, thenBlock = stat.thenBlock } }
					for _, branch in stat.elseifs do
						table.insert(branches, branch)
					end
					local remaining = true
					for _, branch in branches do
						if not remaining then break end
						expression(branch.condition, s)
						if truth(branch.condition) ~= false then
							local live, br, co = block(branch.thenBlock, { clone(s) })
							merge(nextStates, live) merge(breaks, br) merge(continues, co)
						end
						remaining = truth(branch.condition) ~= true
					end
					if remaining then
						if stat.elseBlock then
							local live, br, co = block(stat.elseBlock, { s })
							merge(nextStates, live) merge(breaks, br) merge(continues, co)
						else merge(nextStates, { s }) end
					end
				elseif tag == "while" or tag == "repeat" or tag == "for" or tag == "forin" then
					if tag ~= "repeat" then expression(stat.condition, s) end
					if tag == "for" then
						expression(stat.from, s) expression(stat.to, s) expression(stat.step, s)
					elseif tag == "forin" then
						for _, pair in stat.values do expression(pair.node, s) end
					end
					if tag == "while" and truth(stat.condition) == false then
						merge(nextStates, { s })
						continue
					end
					local live, br, co = block(stat.body, { clone(s) })
					merge(live, co)
					for _, back in live do
						if tag == "repeat" then expression(stat.condition, back) end
						local mismatch = if mode == "profile" then back.depth ~= s.depth else back.owed ~= s.owed
						if mismatch and not (tag == "repeat" and truth(stat.condition) == true) then
							report(stat, "unbalanced loop scope", "restore profile/explicit parallel scope before continue or next iteration")
						end
					end
					-- while/for may run zero times. A repeat always executes its body.
					if tag ~= "repeat" and not (tag == "while" and truth(stat.condition) == true) then
						merge(nextStates, { s })
					end
					if not ((tag == "while" and truth(stat.condition) == true)
						or (tag == "repeat" and truth(stat.condition) == false)) then
						merge(nextStates, live)
					end
					merge(nextStates, br)
				elseif tag == "do" then
					local live, br, co = block(stat.body, { s })
					merge(nextStates, live) merge(breaks, br) merge(continues, co)
				elseif tag == "return" then
					for _, pair in stat.expressions do expression(pair.node, s) end
					exitScope(stat, s)
				elseif tag == "break" then
					merge(breaks, { s })
				elseif tag == "continue" then
					merge(continues, { s })
				else
					if tag == "expression" then expression(stat.expression, s)
					elseif tag == "local" or tag == "assign" then
						for _, pair in stat.values do expression(pair.node, s) end
					elseif tag == "compoundassign" then expression(stat.value, s) end
					if writes and mode == "parallel" and s.parallel == true then
						local variables = if tag == "assign" then lib.nodes(stat.variables)
							else if tag == "compoundassign" then { stat.variable } else {}
						for _, target in variables do
							if target.tag == "indexname" and target.index.text:match("^%u") then
								report(target, "possible DataModel write in parallel", "check API thread safety; synchronize before unsafe writes")
							end
						end
					end
					if tag == "expression" and lib.globalCall(stat.expression) == "error" then
						exitScope(stat, s)
					else merge(nextStates, { s }) end
				end
			end
			states = nextStates
		end
		return states, breaks, continues
	end
	local function check(body, parallel)
		local live = block(body, { { depth = 0, parallel = parallel, owed = false } })
		for _, s in live do exitScope(body, s) end
	end
	local parallelBodies = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local method = lib.methodCall(node)
		if method == "ConnectParallel" or method == "BindToMessageParallel" then
			local args = lib.nodes(node.arguments)
			local fn = args[if method == "ConnectParallel" then 1 else 2]
			if fn and fn.tag == "function" then parallelBodies[fn.body] = true end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	check(ast, false)
	local functions = visitor.create()
	functions.visitExprFunction = function(node)
		check(node.body, parallelBodies[node.body])
		return true
	end
	visitor.visitBlock(ast, functions)
	return out
end

return flow
