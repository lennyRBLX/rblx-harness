-- WRIT20: function signatures/bodies, without names or trivia; comparison is advisory.
local fs = require("@std/fs")
local syntax = require("@std/syntax")
local visitor = require("@std/syntax/visitor")

local function fingerprint(node, lines)
	local tokens, seen = {}, {}
	local function collect(value)
		if typeof(value) ~= "table" or seen[value] then return end
		seen[value] = true
		if value.text and value.location then
			table.insert(tokens, value)
			return
		end
		for key, child in value do
			if key ~= "local" and key ~= "leadingTrivia" and key ~= "trailingTrivia" then
				collect(child)
			end
		end
	end
	collect(node)
	table.sort(tokens, function(a, b)
		local x, y = a.location, b.location
		return x.beginLine < y.beginLine or x.beginLine == y.beginLine and x.beginColumn < y.beginColumn
	end)
	local texts = {}
	for _, token in tokens do
		local loc = token.location
		local parts = {}
		for line = loc.beginLine, loc.endLine do
			local first = if line == loc.beginLine then loc.beginColumn else 1
			local last = if line == loc.endLine then loc.endColumn - 1 else #lines[line]
			table.insert(parts, lines[line]:sub(first, last))
		end
		local text = table.concat(parts, "\n")
		table.insert(texts, #text .. ":" .. text .. #token.text .. ":" .. token.text)
	end
	return (table.concat(texts):gsub(".", function(c) return string.format("%02x", string.byte(c)) end))
end

local args = { ... }
for i = 2, #args do
	local source = fs.readFileToString(args[i])
	local lines = string.split(source, "\n")
	local parsed = syntax.parse(source)
	local v = visitor.create()
	v.visitExprFunction = function(node)
		if #node.body.statements > 0 then
			print(i - 1, node.location.beginLine, node.location.beginColumn, fingerprint(node, lines))
		end
		return true
	end
	visitor.visitBlock(parsed.root, v)
end
