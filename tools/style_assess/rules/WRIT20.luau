-- WRIT20: collapse parallel tables — never a key-list beside a key-value map
-- of the same keys.
local lib = require("../stylelib")

local name = "WRIT20"

local function tableEntries(stat)
	if stat.tag ~= "local" then
		return nil, nil, nil
	end
	for i, pair in stat.variables do
		local valuePair = stat.values[i]
		if valuePair and valuePair.node.tag == "table" then
			return pair.node.name.text, valuePair.node, pair.node.location
		end
	end
	return nil, nil, nil
end

local function lint(ast, sourcepath, context)
	local lists, maps = {}, {}
	for _, stat in ast.statements do
		local tname, tbl, loc = tableEntries(stat)
		if tname ~= nil then
			local listValues, mapKeys = {}, {}
			local isList, isMap = true, true
			for _, entry in tbl.entries do
				if entry.kind == "list" then
					isMap = false
					local value = lib.stringValue(entry.value)
					if value then
						listValues[value] = true
					end
				elseif entry.kind == "record" then
					isList = false
					mapKeys[entry.key.text] = true
				else
					isList, isMap = false, false
				end
			end
			if isList and next(listValues) ~= nil then
				table.insert(lists, { name = tname, values = listValues, location = loc })
			elseif isMap and next(mapKeys) ~= nil then
				table.insert(maps, { name = tname, keys = mapKeys, location = loc })
			end
		end
	end
	local out = {}
	for _, list in lists do
		for _, map in maps do
			local all = true
			for value in list.values do
				if not map.keys[value] then
					all = false
					break
				end
			end
			if all then
				table.insert(
					out,
					lib.violation(
						name,
						list.location,
						list.name .. " beside " .. map.name,
						"collapse the key-list into the map",
						sourcepath
					)
				)
				break
			end
		end
	end
	return out
end

return table.freeze({ name = name, lint = lint })
