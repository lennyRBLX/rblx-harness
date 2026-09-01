-- OPT12 (nil-check clause): a :FindFirstChild result used before a nil test.
-- Guarantee on a local binding, skip otherwise — the dot-index clause lives
-- in deny_scan.
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "OPT12"

local function usesLocal(node, decl)
	local found = false
	local v = visitor.create()
	v.visitExprLocal = function(n)
		if n["local"] == decl then
			found = true
		end
		return true
	end
	visitor.visitStatement(node, v)
	return found
end

local function isNilTest(stat, decl)
	-- an if whose condition references the local counts as the nil test
	if stat.tag == "conditional" then
		local found = false
		local v = visitor.create()
		v.visitExprLocal = function(n)
			if n["local"] == decl then
				found = true
			end
			return true
		end
		visitor.visitExpression(stat.condition, v)
		return found
	end
	return false
end

local function scanBlock(block, out, sourcepath)
	for i, stat in block.statements do
		if stat.tag == "local" and #stat.variables == 1 then
			local valuePair = stat.values[1]
			local value = valuePair and valuePair.node
			if value ~= nil and value.tag == "call" then
				local method = lib.methodCall(value)
				if method == "FindFirstChild" then
					local decl = stat.variables[1].node
					for j = i + 1, #block.statements do
						local nxt = block.statements[j]
						if isNilTest(nxt, decl) then
							break
						end
						if usesLocal(nxt, decl) then
							table.insert(
								out,
								lib.violation(
									name,
									nxt.location,
									stat.variables[1].node.name.text .. " used before nil test",
									"FindFirstChild result takes a nil-check",
									sourcepath
								)
							)
							break
						end
					end
				end
			end
		end
	end
end

local function lint(ast, sourcepath, context)
	local out = {}
	local v = visitor.create()
	v.visitStatBlock = function(block)
		scanBlock(block, out, sourcepath)
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
