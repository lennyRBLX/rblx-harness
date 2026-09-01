-- data_write_core — the in-memory half of data_write: loads the current pair,
-- applies the edit to each, validates (GATE1 in --load form, type parity
-- across the WHOLE pair), renders both modules in house style, and emits the
-- export type into Default from the shape it just validated. The Python
-- wrapper owns data_shape_diff and the rename dance.
--
--   lute run data_write_core.luau <keypath> <defaultLit> <devLit>
--       <curDefault|NEW> <curDev|NEW> <outDefault> <outDev>
--
-- The values are parsed from the CST, never evaluated — a non-literal value
-- is refused here, which is DATA4 enforced at the entry.
local fs = require("@std/fs")
local luau = require("@std/luau")
local process = require("@std/process")
local syntax = require("@std/syntax")

local ARGS = { ... }

local function fail(line, col, subject, reason)
	print(string.format("%d|%d|GATE1|%s|%s", line, col, subject, reason))
	process.exit(2)
end

-- ------------------------------------------------------- literal parsing --

local function evalLiteral(node, what)
	local tag = node.tag
	if tag == "string" then
		return node.token.text
	elseif tag == "number" then
		return node.value
	elseif tag == "boolean" then
		return node.value
	elseif tag == "nil" then
		return nil
	elseif tag == "unary" and node.operator.text == "-" and node.operand.tag == "number" then
		return -node.operand.value
	elseif tag == "table" then
		local out = {}
		local listIndex = 0
		for _, entry in node.entries do
			if entry.kind == "record" then
				out[entry.key.text] = evalLiteral(entry.value, what)
			elseif entry.kind == "list" then
				listIndex += 1
				out[listIndex] = evalLiteral(entry.value, what)
			else
				local key = evalLiteral(entry.key, what)
				out[key] = evalLiteral(entry.value, what)
			end
		end
		return out
	end
	fail(node.location.beginLine, node.location.beginColumn, what, "not a static literal [DATA4]")
	return nil
end

local function parseLiteral(text, what)
	local ok, parsed = pcall(syntax.parse, "return " .. text)
	if not ok then
		fail(0, 0, what, "unparseable literal")
	end
	local ret = parsed.root.statements[1]
	if ret == nil or ret.tag ~= "return" then
		fail(0, 0, what, "unparseable literal")
	end
	local first = ret.expressions[1]
	if first == nil then
		fail(0, 0, what, "empty literal")
	end
	return evalLiteral(first.node, what)
end

-- ------------------------------------------------------------ GATE1 check --

local function checkValue(value, path)
	local t = typeof(value)
	if t == "string" then
		if utf8.len(value) == nil then
			fail(0, 0, path, "not UTF-8")
		end
	elseif t == "number" then
		if value ~= value or value == math.huge or value == -math.huge then
			fail(0, 0, path, "not finite")
		end
	elseif t == "boolean" or t == "buffer" then
		return
	elseif t == "table" then
		local stringKeys, intKeys, maxInt = 0, 0, 0
		for k in value do
			local kt = typeof(k)
			if kt == "string" then
				stringKeys += 1
			elseif kt == "number" and k % 1 == 0 and k >= 1 then
				intKeys += 1
				maxInt = math.max(maxInt, k)
			else
				fail(0, 0, path, "key type not string or sequential integer")
			end
		end
		if stringKeys > 0 and intKeys > 0 then
			fail(0, 0, path, "mixed keys")
		end
		if intKeys > 0 and maxInt ~= intKeys then
			fail(0, 0, path, "sparse array")
		end
		for k, v in value do
			checkValue(v, path .. "." .. tostring(k))
		end
	else
		fail(0, 0, path, t .. ", not JSONAcceptable")
	end
end

-- ------------------------------------------------------------ type parity --

local function typeShape(value)
	local t = typeof(value)
	if t ~= "table" then
		return t
	end
	local parts = {}
	for k, v in value do
		table.insert(parts, tostring(k) .. ":" .. typeShape(v))
	end
	table.sort(parts)
	return "{" .. table.concat(parts, ",") .. "}"
end

local function checkParity(default, dev, path)
	-- typeof parity on intersecting keys, recursively — two modules
	-- disagreeing on a key's type would reset it on every join in one place
	-- and not the other [DATA6]. Record keys pair BY CONSTRUCTION (this tool
	-- lands every edit in both files); a key present on one side only is a
	-- container entry — dev's filled example, or default's starter value —
	-- and containers hold values, not shape.
	local dt, vt = typeof(default), typeof(dev)
	if dt ~= vt then
		fail(0, 0, path, "type parity broken: default " .. dt .. ", dev " .. vt .. " - fix() would reset it every load [DATA6]")
	end
	if dt == "table" then
		for k, v in default do
			if dev[k] ~= nil then
				checkParity(v, dev[k], path .. "." .. tostring(k))
			end
		end
	end
end

-- -------------------------------------------------------------- rendering --

local function isArray(t)
	local n = 0
	for k in t do
		if typeof(k) ~= "number" then
			return false
		end
		n += 1
	end
	return n == #t
end

local function renderValue(value, indent)
	local t = typeof(value)
	if t == "string" then
		return string.format("%q", value)
	elseif t == "number" or t == "boolean" then
		return tostring(value)
	elseif t == "table" then
		if next(value) == nil then
			return "{}"
		end
		local pad = string.rep("\t", indent + 1)
		local lines = {}
		if isArray(value) then
			for _, v in ipairs(value) do
				table.insert(lines, pad .. renderValue(v, indent + 1) .. ",")
			end
		else
			local keys = {}
			for k in value do
				table.insert(keys, k)
			end
			table.sort(keys, function(a, b)
				return tostring(a) < tostring(b)
			end)
			for _, k in keys do
				local keyText = tostring(k)
				if not keyText:match("^[%a_][%w_]*$") then
					keyText = "[" .. string.format("%q", keyText) .. "]"
				end
				table.insert(lines, pad .. keyText .. " = " .. renderValue(value[k], indent + 1) .. ",")
			end
		end
		return "{\n" .. table.concat(lines, "\n") .. "\n" .. string.rep("\t", indent) .. "}"
	end
	error("unrenderable " .. t)
end

local function renderType(value, indent, example)
	-- an empty default container takes its type from dev's filled example —
	-- the child shape is the decision the human ruled on
	local t = typeof(value)
	if t == "table" then
		if next(value) == nil then
			if typeof(example) == "table" and next(example) ~= nil then
				value = example
			else
				return "{ [string]: never }"
			end
		end
		if isArray(value) then
			return "{ " .. renderType(value[1], indent, typeof(example) == "table" and example[1] or nil) .. " }"
		end
		local pad = string.rep("\t", indent + 1)
		local keys = {}
		for k in value do
			table.insert(keys, k)
		end
		table.sort(keys, function(a, b)
			return tostring(a) < tostring(b)
		end)
		local lines = {}
		local isContainer = false
		for _, k in keys do
			if not tostring(k):match("^[%u]") then
				isContainer = true
			end
		end
		if isContainer and #keys > 0 then
			-- data-keyed map: type the value shape, not the example keys
			local sample = value[keys[1]]
			return "{ [string]: " .. renderType(sample, indent, nil) .. " }"
		end
		for _, k in keys do
			local keyText = tostring(k)
			if not keyText:match("^[%a_][%w_]*$") then
				keyText = "[" .. string.format("%q", keyText) .. "]"
			end
			table.insert(lines, pad .. keyText .. ": " .. renderType(value[k], indent + 1, typeof(example) == "table" and example[k] or nil) .. ",")
		end
		return "{\n" .. table.concat(lines, "\n") .. "\n" .. string.rep("\t", indent) .. "}"
	end
	return t
end

-- ------------------------------------------------------------------- main --

local keypath, defaultLit, devLit = ARGS[2], ARGS[3], ARGS[4]
local curDefault, curDev, outDefault, outDev = ARGS[5], ARGS[6], ARGS[7], ARGS[8]
assert(outDev ~= nil, "usage: data_write_core <keypath> <defLit> <devLit> <curDef|NEW> <curDev|NEW> <outDef> <outDev>")

local function loadCurrent(path)
	if path == "NEW" then
		return {}
	end
	local ok, result = pcall(luau.loadModule, path)
	if not ok or typeof(result) ~= "table" then
		fail(0, 0, path, "current module will not load: " .. tostring(result):gsub("\n", " "):sub(1, 100))
	end
	return result
end

local default = loadCurrent(curDefault)
local dev = loadCurrent(curDev)

local defaultValue = parseLiteral(defaultLit, keypath)
local devValue = parseLiteral(devLit, keypath)

-- a table-valued key needs a non-empty --dev: the child shape is the decision
-- that matters, and an empty container is nothing for a human to rule on
if typeof(defaultValue) == "table" and (typeof(devValue) ~= "table" or next(devValue) == nil) then
	fail(0, 0, keypath, "table-valued key needs a non-empty --dev - the filled example is what the human rules on")
end

local function applyEdit(root, value)
	local parts = {}
	for part in keypath:gmatch("[^.]+") do
		table.insert(parts, part)
	end
	local cur = root
	for i = 1, #parts - 1 do
		local k = parts[i]
		if typeof(cur[k]) ~= "table" then
			cur[k] = {}
		end
		cur = cur[k]
	end
	cur[parts[#parts]] = value
end

applyEdit(default, defaultValue)
applyEdit(dev, devValue)

checkValue(default, "Default")
checkValue(dev, "Development")
checkParity(default, dev, "")

-- per-key aliases serve AddSetup param annotations (the TYPE10-legal typed
-- path); Typed.luau serves inference with zero annotations. script.Name is
-- the file's own name, so the owner is statically known to the tooling even
-- though the type system sees only `string` — the generated member name is
-- the checkable form of the same fact.
local topKeys = {}
for k in default do
	table.insert(topKeys, tostring(k))
end
table.sort(topKeys)

local aliasLines = {}
local dataFields = {}
for _, k in topKeys do
	if k:match("^[%u][%w]*$") and k ~= "Data" then
		table.insert(aliasLines, "export type " .. k .. " = " .. renderType(default[k], 0, dev[k]))
		table.insert(dataFields, "\t" .. k .. ": " .. k .. ",")
	else
		table.insert(dataFields, "\t" .. (k:match("^[%a_][%w_]*$") and k or "[" .. string.format("%q", k) .. "]") .. ": " .. renderType(default[k], 0, dev[k]) .. ",")
	end
end
local typeBlock = table.concat(aliasLines, "\n") .. (#aliasLines > 0 and "\n" or "") .. "export type Data = {\n" .. table.concat(dataFields, "\n") .. "\n}\n"
local defaultSource = "-- generated by data_write; the only writer [GATE3]\n" .. typeBlock .. "\nreturn " .. renderValue(default, 0) .. "\n"
local devSource = "-- generated by data_write; the only writer [GATE3]\nreturn " .. renderValue(dev, 0) .. "\n"

local typedLines = {
	"-- generated by data_write; the only writer [GATE3]",
	"-- typed per-service accessors: the member name is the statically checkable",
	"-- form of script.Name, and replication_audit holds it to the file's owner",
	"local Default = require(script.Parent.Default)",
	"local PlayerData = require(script.Parent)",
	"",
	"local m = {}",
}
for _, k in topKeys do
	if k:match("^[%u][%w]*$") then
		table.insert(typedLines, "")
		table.insert(typedLines, "function m." .. k .. "(player: Player)")
		table.insert(typedLines, "\t-- generated seam: the runtime returns exactly this subtree [TYPE9]")
		table.insert(typedLines, "\treturn PlayerData:Get(player, " .. string.format("%q", k) .. ") :: typeof(Default." .. k .. ")")
		table.insert(typedLines, "end")
	end
end
table.insert(typedLines, "")
table.insert(typedLines, "return m")

fs.writeStringToFile(outDefault, defaultSource)
fs.writeStringToFile(outDev, devSource)
local outTyped = outDefault:gsub("Default%.luau$", "Typed.luau")
fs.writeStringToFile(outTyped, table.concat(typedLines, "\n") .. "\n")

-- verify both parse and load back
for _, p in { outDefault, outDev } do
	local ok, result = pcall(luau.loadModule, p)
	assert(ok and typeof(result) == "table", "rendered module failed to load: " .. p)
end

print("OK")
print(keypath .. "|" .. defaultLit)
print(keypath .. "|" .. devLit)
