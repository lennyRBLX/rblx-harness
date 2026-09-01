-- data_check — the GATE1 serializability checker, split out of data_write so
-- gates can reach it. Profile.Data holds only UTF-8 string, finite number,
-- boolean, buffer, and acyclic tables keyed all-string or
-- all-sequential-integer.
--
--   lute run data_check.luau --load <module.luau>     walk the real returned
--                                                     table (guarantee)
--   lute run data_check.luau --static <file.luau>     CST resolution as far
--                                                     as literals allow (lean;
--                                                     false-negative only)
--
-- --load falls back to --static when the module will not load, and SAYS SO
-- rather than silently downgrading a guarantee to a lean.
-- Findings: line|col|GATE1|subject|reason (0|0 in --load mode — values, not
-- source). Exit 0 clean, 2 findings.
local fs = require("@std/fs")
local luau = require("@std/luau")
local syntax = require("@std/syntax")
local visitor = require("@std/syntax/visitor")

local ARGS = { ... }

local findings = {}

local function finding(line, col, subject, reason)
	table.insert(findings, string.format("%d|%d|GATE1|%s|%s", line, col, subject, reason))
end

-- ------------------------------------------------------------------ --load --

local function checkValue(value, path, seen)
	local t = typeof(value)
	if t == "string" then
		if utf8.len(value) == nil then
			finding(0, 0, path, "Encode as valid UTF-8; retry.")
		end
	elseif t == "number" then
		if value ~= value then
			finding(0, 0, path, "Replace w/ a finite number; retry.")
		elseif value == math.huge or value == -math.huge then
			finding(0, 0, path, "Replace w/ a finite number; retry.")
		end
	elseif t == "boolean" or t == "buffer" then
		-- fine
	elseif t == "table" then
		if seen[value] then
			finding(0, 0, path, "Remove the cycle; retry.")
			return
		end
		seen[value] = true
		local stringKeys, intKeys, otherKeys = 0, 0, 0
		local maxInt = 0
		local total = 0
		for k in value do
			total += 1
			local kt = typeof(k)
			if kt == "string" then
				stringKeys += 1
				if utf8.len(k) == nil then
					finding(0, 0, path .. "." .. tostring(k), "Encode the key as valid UTF-8; retry.")
				end
			elseif kt == "number" then
				if k % 1 == 0 and k >= 1 then
					intKeys += 1
					maxInt = math.max(maxInt, k)
				else
					otherKeys += 1
					finding(0, 0, path .. "[" .. tostring(k) .. "]", "Use a string / positive int key; retry.")
				end
			else
				otherKeys += 1
				finding(0, 0, path .. "[" .. typeof(k) .. "]", "Use a string / positive int key; retry.")
			end
		end
		if stringKeys > 0 and intKeys > 0 then
			finding(0, 0, path, "Use all string keys / sequential int keys; retry.")
		elseif intKeys > 0 and maxInt ~= intKeys then
			finding(0, 0, path, "Reindex from 1 w/o gaps; retry.")
		end
		for k, v in value do
			local sub = typeof(k) == "string" and (path .. "." .. k) or (path .. "[" .. tostring(k) .. "]")
			checkValue(v, sub, seen)
		end
	else
		finding(0, 0, path .. " = " .. tostring(value), "Convert to a string, finite number, boolean, buffer or serializable table; retry.")
	end
end

local function runLoad(modulePath)
	local ok, result = pcall(luau.loadModule, modulePath)
	if not ok or typeof(result) ~= "table" then
		return false, tostring(result)
	end
	checkValue(result, "", { })
	return true
end

-- ---------------------------------------------------------------- --static --

local REJECT_CONSTRUCTORS = {
	Vector3 = true, Vector2 = true, CFrame = true, Color3 = true, UDim = true,
	UDim2 = true, BrickColor = true, Instance = true, Region3 = true, Rect = true,
	NumberRange = true, NumberSequence = true, ColorSequence = true, Ray = true,
	TweenInfo = true, Random = true, Font = true, OverlapParams = true, RaycastParams = true,
}

local function staticCheckExpr(node, subject)
	-- false-negative only: fires when the type is statically known and wrong,
	-- silent when unknown
	if node == nil then
		return
	end
	local tag = node.tag
	if tag == "string" or tag == "boolean" or tag == "nil" then
		return
	elseif tag == "number" then
		return
	elseif tag == "unary" and node.operand.tag == "number" then
		return
	elseif tag == "table" then
		local hasRecord, hasList = false, false
		for _, entry in node.entries do
			if entry.kind == "record" then
				hasRecord = true
				staticCheckExpr(entry.value, subject .. "." .. entry.key.text)
			elseif entry.kind == "list" then
				hasList = true
				staticCheckExpr(entry.value, subject .. "[]")
			else
				staticCheckExpr(entry.value, subject .. "[?]")
				if entry.key ~= nil and entry.key.tag ~= "string" and entry.key.tag ~= "number" then
					finding(entry.location.beginLine, entry.location.beginColumn, subject, "Use a literal key; retry.")
				end
			end
		end
		if hasRecord and hasList then
			finding(node.location.beginLine, node.location.beginColumn, subject, "Use all string keys / sequential int keys; retry.")
		end
		return
	elseif tag == "call" then
		local f = node.func
		if f.tag == "indexname" and f.index.text == "new" and f.expression.tag == "global" then
			local ctor = f.expression.name.text
			if REJECT_CONSTRUCTORS[ctor] then
				finding(node.location.beginLine, node.location.beginColumn, ctor .. ".new(...)", "Store primitive fields; retry.")
				return
			end
		end
		-- unknown call: silent — done-gate's typed destination catches it
		return
	elseif tag == "function" then
		finding(node.location.beginLine, node.location.beginColumn, subject, "Remove the fn; store serializable data; retry.")
		return
	elseif tag == "indexname" then
		local chain = {}
		local cur = node
		while cur ~= nil and cur.tag == "indexname" do
			table.insert(chain, 1, cur.index.text)
			cur = cur.expression
		end
		if cur ~= nil and cur.tag == "global" then
			local head = cur.name.text
			if head == "math" and (chain[1] == "huge") then
				finding(node.location.beginLine, node.location.beginColumn, "math.huge", "Replace w/ a finite number; retry.")
			end
		end
		return
	end
end

local function runStatic(filePath)
	local source = fs.readFileToString(filePath)
	local okParse, parsed = pcall(syntax.parse, source)
	if not okParse then
		finding(0, 0, filePath, "Fix Luau syntax; retry.")
		return
	end

	-- template form: a returned (or local-then-returned) table is checked
	-- whole — a Vector3.new default is definitely wrong even statically
	for _, stat in parsed.root.statements do
		if stat.tag == "return" then
			for _, pair in stat.expressions do
				if pair.node.tag == "table" then
					staticCheckExpr(pair.node, "template")
				end
			end
		elseif stat.tag == "local" then
			for i, pair in stat.variables do
				local valuePair = stat.values[i]
				if valuePair and valuePair.node.tag == "table" then
					staticCheckExpr(valuePair.node, pair.node.name.text)
				end
			end
		end
	end

	-- taint sources: local d = PlayerData:Get(...), AddSetup callback params,
	-- and (inside PlayerData/) <profile>.Data
	local tainted = {} -- AstLocal -> true

	local v = visitor.create()
	v.visitStatLocalDeclaration = function(stat)
		for i, pair in stat.variables do
			local valuePair = stat.values[i]
			local value = valuePair and valuePair.node
			if value ~= nil and value.tag == "call" then
				local f = value.func
				if f.tag == "indexname" and f.accessor.text == ":" and f.index.text == "Get" then
					local recv = f.expression
					if recv.tag == "local" and recv.token.text == "PlayerData" or recv.tag == "global" and recv.name.text == "PlayerData" then
						tainted[pair.node] = true
					end
				end
			end
		end
		return true
	end
	v.visitExprCall = function(call)
		local f = call.func
		if f.tag == "indexname" and f.accessor.text == ":" and f.index.text == "AddSetup" then
			for _, pair in call.arguments do
				if pair.node.tag == "function" then
					local params = pair.node.parameters
					local second = params[2]
					if second ~= nil then
						tainted[second.node] = true
					end
				end
			end
		end
		return true
	end
	visitor.visitBlock(parsed.root, v)

	local v2 = visitor.create()
	v2.visitStatAssign = function(stat)
		for i, pair in stat.variables do
			local target = pair.node
			local root = target
			while root.tag == "indexname" or root.tag == "index" do
				root = root.expression
			end
			local isTainted = root.tag == "local" and tainted[root["local"]] == true
			-- <profile>.Data writes inside PlayerData/ resolve by name
			if not isTainted and target.tag == "indexname" and target.index.text ~= nil then
				local chainRoot = target.expression
				if chainRoot.tag == "indexname" and chainRoot.index.text == "Data" then
					isTainted = true
				end
			end
			if isTainted then
				local valuePair = stat.values[i]
				if valuePair ~= nil then
					local chain = {}
					local cur = target
					while cur ~= nil and (cur.tag == "indexname") do
						table.insert(chain, 1, cur.index.text)
						cur = cur.expression
					end
					staticCheckExpr(valuePair.node, table.concat(chain, ".") ~= "" and table.concat(chain, ".") or "value")
				end
			end
		end
		return true
	end
	visitor.visitBlock(parsed.root, v2)
end

-- ------------------------------------------------------------------- main --

local mode, target = ARGS[2], ARGS[3]
assert(target ~= nil, "usage: lute run data_check.luau --load|--static <file>")

if mode == "--load" then
	local ok, err = runLoad(target)
	if not ok then
		print("SKIPPED --load, ran --static - " .. tostring(err):gsub("\n", " "):sub(1, 120))
		runStatic(target)
	end
elseif mode == "--static" then
	runStatic(target)
else
	error("unknown mode " .. tostring(mode))
end

if #findings > 0 then
	for _, f in findings do
		print(f)
	end
	require("@std/process").exit(2)
end
