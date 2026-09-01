-- data_shape_diff — one verdict, ALLOW or BLOCK. Schema changes are evidence
-- for the required human ruling; only configured hard boundaries block. The
-- baseline is the current file, not git.
--
--   lute run data_shape_diff.luau <baseline-default> <proposed-default>
--       [--migrations <dir>]
--
--   retype              ALLOW + note for human ruling         [R DATA34]
--   add                 ALLOW — backfilled from the template
--   drop                ALLOW + migration/ruling note         [R DATA34]
--   non-literal default BLOCK at serialization boundary       [R GATE1]
--   per-place fork      BLOCK                                 [R DATA5]
--   value change        ALLOW
--
-- The writer workflow obtains the human ruling before this tool. DATA34 is
-- evidence for that ruling, not an unconditional machine veto.
-- The generated export type block is not diffed — it is derived from the
-- shape being compared. Fails closed.
local fs = require("@std/fs")
local luau = require("@std/luau")
local process = require("@std/process")
local syntax = require("@std/syntax")
local visitor = require("@std/syntax/visitor")

local ARGS = { ... }

local reasons = {}
local verdict = "ALLOW"

local function block(reason)
	verdict = "BLOCK"
	table.insert(reasons, reason)
end

local function note(reason)
	table.insert(reasons, reason)
end

-- ------------------------------------------------------- shape extraction --

local function shapeOf(value)
	local t = typeof(value)
	if t == "table" then
		local shape = { kind = "table", keys = {} }
		for k, v in value do
			shape.keys[tostring(k)] = shapeOf(v)
		end
		return shape
	end
	return { kind = t }
end

local function diffShapes(base, proposed, path, drops)
	if base.kind ~= proposed.kind then
		note(path .. " retyped " .. base.kind .. " -> " .. proposed.kind .. " - human schema ruling required [DATA34]")
		return
	end
	if base.kind ~= "table" then
		return
	end
	for k, bshape in base.keys do
		local pshape = proposed.keys[k]
		if pshape == nil then
			table.insert(drops, path .. "." .. k)
		else
			diffShapes(bshape, pshape, path .. "." .. k, drops)
		end
	end
	-- adds are ALLOW: backfilled from the template, no existing value touched
end

-- --------------------------------------------- non-literal default (DATA4) --

local function checkLiterals(filePath)
	local source = fs.readFileToString(filePath)
	local parsed = syntax.parse(source)
	local violations = 0
	local function checkExpr(node)
		local tag = node.tag
		if tag == "string" or tag == "number" or tag == "boolean" or tag == "nil" then
			return
		elseif tag == "unary" and node.operand.tag == "number" then
			return
		elseif tag == "table" then
			for _, entry in node.entries do
				checkExpr(entry.value)
			end
			return
		else
			block(string.format("%d|%d non-literal default - defaults must cross the static serialization boundary [GATE1]", node.location.beginLine, node.location.beginColumn))
			violations += 1
		end
	end
	-- the template is `return { ... }` (or local T = {...}; return T) with no
	-- requires and no Roblox globals; every value expression must be literal.
	-- export type statements are skipped: generated from the shape, not diffed.
	local v = visitor.create()
	v.visitStatReturn = function(stat)
		for _, pair in stat.expressions do
			if pair.node.tag == "table" then
				checkExpr(pair.node)
			end
		end
		return true
	end
	v.visitStatLocalDeclaration = function(stat)
		for i, pair in stat.variables do
			local valuePair = stat.values[i]
			if valuePair and valuePair.node.tag == "table" then
				checkExpr(valuePair.node)
			end
		end
		return true
	end
	visitor.visitBlock(parsed.root, v)
	return violations
end

-- --------------------------------------------------- Pre-fix migration scan --

local function migrationWritesKey(dir, keyName)
	if dir == nil or not fs.exists(dir) then
		return false
	end
	for _, entry in fs.listDirectory(dir) do
		local p = dir .. "/" .. entry.name
		if entry.type == "dir" then
			if migrationWritesKey(p, keyName) then
				return true
			end
		elseif entry.name:match("%.luau$") or entry.name:match("%.lua$") then
			local ok, source = pcall(fs.readFileToString, p)
			if ok then
				local parsedOk, parsed = pcall(syntax.parse, source)
				if parsedOk then
					local found = false
					local v = visitor.create()
					v.visitExprCall = function(call)
						local f = call.func
						if f.tag == "indexname" and f.index.text == "AddSetup" then
							local args = {}
							for _, pair in call.arguments do
								table.insert(args, pair.node)
							end
							local phase = args[1]
							if phase ~= nil and phase.tag == "string" and phase.token.text == "Pre" then
								local cb = args[2]
								if cb ~= nil and cb.tag == "function" then
									local vv = visitor.create()
									vv.visitStatAssign = function(stat)
										for _, vpair in stat.variables do
											local t = vpair.node
											if t.tag == "indexname" and t.index.text == keyName then
												found = true
											end
										end
										return true
									end
									visitor.visitBlock(cb.body, vv)
								end
							end
						end
						return true
					end
					visitor.visitBlock(parsed.root, v)
					if found then
						return true
					end
				end
			end
		end
	end
	return false
end

-- ------------------------------------------------------------------- main --

local baselinePath, proposedPath = ARGS[2], ARGS[3]
local migrationsDir = nil
for i = 4, #ARGS do
	if ARGS[i] == "--migrations" then
		migrationsDir = ARGS[i + 1]
	end
end
assert(baselinePath ~= nil and proposedPath ~= nil, "usage: lute run data_shape_diff.luau <baseline> <proposed> [--migrations <dir>]")

-- per-place fork is a path test [R DATA5]
if proposedPath:gsub("\\", "/"):find("/places/", 1, true) then
	block("per-place template fork - one template serves every place [DATA5]")
end

checkLiterals(proposedPath)

local okBase, base = pcall(luau.loadModule, baselinePath)
local okProp, proposed = pcall(luau.loadModule, proposedPath)
if not okBase or typeof(base) ~= "table" then
	block("baseline module will not load: " .. tostring(base):gsub("\n", " "):sub(1, 100))
elseif not okProp or typeof(proposed) ~= "table" then
	block("proposed module will not load: " .. tostring(proposed):gsub("\n", " "):sub(1, 100))
else
	local drops = {}
	diffShapes(shapeOf(base), shapeOf(proposed), "", drops)
	for _, dropped in drops do
		local keyName = dropped:match("([^.]+)$")
		if migrationWritesKey(migrationsDir, keyName) then
			table.insert(reasons, dropped .. " dropped with Pre-fix migration - stored value survives")
		else
			note(dropped .. " dropped with no Pre-fix migration writing the paired new key - human schema ruling required [DATA34]")
		end
	end
end

print(verdict)
for _, r in reasons do
	print(r)
end
process.exit(verdict == "ALLOW" and 0 or 2)
