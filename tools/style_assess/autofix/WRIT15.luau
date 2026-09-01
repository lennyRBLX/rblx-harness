-- WRIT15 (--fix): a comma is followed by one space (or a line break) and
-- never preceded by one. Ships as suggestedfix + --auto-fix: comma spans are
-- provably disjoint — two commas are always separated by an expression. A
-- comma whose surrounding trivia holds a comment is skipped.
--
-- Two trivia facts drive the shape (measured): the space BEFORE a comma
-- attaches to the PREVIOUS token's trailingTrivia, and Punctuated separator
-- tokens are not reached by visitToken — so tokens and separators are
-- collected, ordered, and inspected as neighbors.
local syntax = require("@std/syntax")
local visitor = require("@std/syntax/visitor")
local lib = require("../stylelib")

local name = "WRIT15"

local function lint(ast, sourcepath, context)
	local out = {}
	local tokens = {}
	local seen = {}

	local function add(token)
		if token ~= nil and not seen[token] and token.text ~= "" then
			seen[token] = true
			table.insert(tokens, token)
		end
	end

	local function sweepPunctuated(punctuated)
		for _, pair in punctuated or {} do
			add(pair.separator)
		end
	end

	local v = visitor.create()
	v.visitToken = function(token)
		add(token)
		return true
	end
	v.visitExprFunction = function(node)
		sweepPunctuated(node.parameters)
		return true
	end
	v.visitStatLocalDeclaration = function(node)
		sweepPunctuated(node.variables)
		sweepPunctuated(node.values)
		return true
	end
	v.visitStatAssign = function(node)
		sweepPunctuated(node.variables)
		sweepPunctuated(node.values)
		return true
	end
	v.visitStatForIn = function(node)
		sweepPunctuated(node.variables)
		sweepPunctuated(node.values)
		return true
	end
	v.visitStatReturn = function(node)
		sweepPunctuated(node.expressions)
		return true
	end
	v.visitExprCall = function(node)
		sweepPunctuated(node.arguments)
		return true
	end
	visitor.visitBlock(ast, v)

	table.sort(tokens, function(a, b)
		if a.location.beginLine ~= b.location.beginLine then
			return a.location.beginLine < b.location.beginLine
		end
		return a.location.beginColumn < b.location.beginColumn
	end)

	for i, token in tokens do
		if token.text ~= "," then
			continue
		end
		local prev = tokens[i - 1]
		-- the whitespace before the comma lives in prev's trailingTrivia
		local leadWs = nil
		local leadComment = false
		if prev ~= nil and prev.location.endLine == token.location.beginLine then
			for _, t in prev.trailingTrivia do
				if t.tag == "comment" or t.tag == "blockcomment" then
					leadComment = true
				elseif t.tag == "whitespace" and not t.text:find("\n", 1, true) then
					leadWs = t
				end
			end
		end
		for _, t in token.leadingTrivia do
			if t.tag == "comment" or t.tag == "blockcomment" then
				leadComment = true
			elseif t.tag == "whitespace" and not t.text:find("\n", 1, true) then
				leadWs = t
			end
		end
		local trailWs, trailComment, trailNewline = nil, false, false
		for _, t in token.trailingTrivia do
			if t.tag == "comment" or t.tag == "blockcomment" then
				trailComment = true
			elseif t.tag == "whitespace" then
				if t.text:find("\n", 1, true) then
					trailNewline = true
				else
					trailWs = t
				end
			end
		end
		-- a trailing-trivia gap can also be observed positionally: the next
		-- token on the same line with nothing recorded means no space
		if not trailNewline and trailWs == nil then
			local nxt = tokens[i + 1]
			if nxt == nil or nxt.location.beginLine ~= token.location.endLine then
				trailNewline = true
			end
		end
		if leadComment then
			continue
		end
		local badLead = leadWs ~= nil
		local badTrail = not trailComment and not trailNewline and (trailWs == nil or trailWs.text ~= " ")
		if not badLead and not badTrail then
			continue
		end
		local beginLine = token.location.beginLine
		local beginColumn = token.location.beginColumn
		local endLine = token.location.endLine
		local endColumn = token.location.endColumn
		if badLead then
			beginLine = leadWs.location.beginLine
			beginColumn = leadWs.location.beginColumn
		end
		local replacement = ","
		if not (trailNewline or trailComment) then
			if trailWs ~= nil then
				endLine = trailWs.location.endLine
				endColumn = trailWs.location.endColumn
			end
			replacement = ", "
		end
		local violation = lib.violation(name, token.location, "comma spacing", "one space after, never before", sourcepath)
		violation.suggestedfix = {
			location = syntax.span.create({
				beginLine = beginLine,
				beginColumn = beginColumn,
				endLine = endLine,
				endColumn = endColumn,
			}),
			fix = replacement,
		}
		table.insert(out, violation)
	end
	return out
end

return table.freeze({ name = name, lint = lint })
