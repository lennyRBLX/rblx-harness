-- WRIT1: the module table is always m; the file ends with return m. Blocks
-- rather than repairs — a formatter cannot safely rename a table.
local lib = require("../stylelib")

local name = "WRIT1"

local function lint(ast, sourcepath, context)
	local stats = ast.statements
	if #stats == 0 then
		return {}
	end
	local last = stats[#stats]
	if last.tag ~= "return" then
		return {}
	end
	local exprs = lib.nodes(last.expressions)
	if #exprs ~= 1 or exprs[1].tag ~= "local" then
		return {}
	end
	local returnedName = exprs[1].token.text
	if returnedName == "m" then
		return {}
	end
	-- only a module table: the returned local's declaration initializer is a
	-- table constructor
	local decl = exprs[1]["local"]
	for _, stat in stats do
		if stat.tag == "local" then
			for i, pair in stat.variables do
				if pair.node == decl then
					local valuePair = stat.values[i]
					if valuePair and valuePair.node.tag == "table" then
						return {
							lib.violation(name, pair.node.location, returnedName, "module table is m", sourcepath),
						}
					end
				end
			end
		end
	end
	return {}
end

return table.freeze({ name = name, lint = lint })
