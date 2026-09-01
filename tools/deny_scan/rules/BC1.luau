-- BC1 (secret-literal clause): a secret-shaped literal in a replicated
-- container. Container decides, not the file suffix; the remote wall is the
-- real defense. The subject never echoes the value.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "BC1"

local HEX = "^[0-9a-fA-F]+$"
local B64 = "^[A-Za-z0-9+/=_%-]+$"

local function secretShaped(value, except)
	if value == nil or #value < 24 then
		return false
	end
	local lower = value:lower()
	for _, ex in except or {} do
		if lower:find(ex, 1, true) then
			return false
		end
	end
	if #value >= 32 and value:find(HEX) then
		return true
	end
	if #value >= 40 and value:find(B64) and value:find("%d") and value:find("%a") then
		return true
	end
	return false
end

local function lint(ast, sourcepath, context)
	local entry = context.options or {}
	if not lib.inPaths(sourcepath, entry.paths) then
		return {}
	end
	local keywords = entry.pattern or { "api_key", "apikey", "secret", "token", "password", "auth_key" }
	local remedy = entry.message or "secrets go in ServerScriptService"
	local out = {}

	local function keyMatch(keyText)
		if keyText == nil then
			return false
		end
		local lower = keyText:lower()
		for _, kw in keywords do
			if lower:find(kw, 1, true) then
				return true
			end
		end
		return false
	end

	local function flag(location, subject)
		table.insert(out, lib.violation(name, location, subject, remedy, sourcepath))
	end

	local v = visitor.create()
	v.visitStatLocalDeclaration = function(node)
		for i, pair in node.variables do
			local valuePair = node.values[i]
			local value = valuePair and lib.stringValue(valuePair.node)
			if value ~= nil and value ~= "" and keyMatch(pair.node.name.text) then
				flag(pair.node.location, "secret-shaped literal " .. pair.node.name.text)
			end
		end
		return true
	end
	v.visitTableExprItem = function(node)
		if node.kind == "record" then
			local value = lib.stringValue(node.value)
			if value ~= nil and value ~= "" and keyMatch(node.key.text) then
				flag(node.location, "secret-shaped literal " .. node.key.text)
			end
		end
		return true
	end
	v.visitExprConstantString = function(node)
		if secretShaped(lib.stringValue(node), entry.except) then
			flag(node.location, "secret-shaped literal")
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
