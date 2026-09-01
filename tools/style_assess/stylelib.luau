-- shared helpers for the style_assess lint rules
local path = require("@std/path")
local syntax = require("@std/syntax")

local lib = {}

function lib.pathString(sourcepath)
	if sourcepath == nil then
		return ""
	end
	return (path.format(sourcepath):gsub("\\", "/"))
end

function lib.inPaths(sourcepath, paths)
	if paths == nil or #paths == 0 then
		return true
	end
	local p = lib.pathString(sourcepath)
	for _, needle in paths do
		if p:find(needle, 1, true) then
			return true
		end
	end
	return false
end

function lib.violation(name, location, subject, remedy, sourcepath)
	return {
		lintname = name,
		location = location,
		message = subject .. "|" .. remedy,
		severity = "warning",
		sourcepath = sourcepath,
	}
end

function lib.at(line, col)
	return syntax.span.create({ beginLine = line, beginColumn = col, endLine = line, endColumn = col })
end

function lib.stringValue(node)
	-- token.text on a string constant is the content, quotes excluded
	if node == nil or node.tag ~= "string" then
		return nil
	end
	return node.token.text
end

-- the three sanctioned dividers, read from comment trivia anywhere in the file:
-- returns { privates = line?, functions = line?, events = line? }
function lib.dividers(ast)
	local found = {}
	local function scanTrivia(trivia)
		for _, t in trivia do
			if t.tag == "comment" then
				local name = t.text:match("^%-%-%s*(%a+)%s*$")
				if name == "privates" or name == "functions" or name == "events" then
					if found[name] == nil then
						found[name] = t.location.beginLine
					end
				end
			end
		end
	end
	local visitor = require("@std/syntax/visitor")
	local v = visitor.create()
	v.visitToken = function(token)
		scanTrivia(token.leadingTrivia)
		scanTrivia(token.trailingTrivia)
		return true
	end
	visitor.visitBlock(ast, v)
	return found
end

-- which section a line falls in, given the divider lines
function lib.sectionOf(line, divs)
	local best, bestLine = nil, -1
	for name, dline in divs do
		if dline <= line and dline > bestLine then
			best, bestLine = name, dline
		end
	end
	return best
end

-- iterate a Punctuated list's nodes
function lib.nodes(punctuated)
	local out = {}
	for _, pair in punctuated or {} do
		table.insert(out, pair.node)
	end
	return out
end

-- the method name of a `recv:Method(...)` call, or nil
function lib.methodCall(callNode)
	if callNode.tag ~= "call" then
		return nil
	end
	local f = callNode.func
	if f.tag == "indexname" and f.accessor.text == ":" then
		return f.index.text, f
	end
	return nil
end

-- global function call name (`pcall(...)` -> "pcall"), or nil
function lib.globalCall(callNode)
	if callNode.tag ~= "call" then
		return nil
	end
	local f = callNode.func
	if f.tag == "global" then
		return f.name.text
	end
	return nil
end

-- render a dotted head for subject strings: workspace.A.B -> "workspace.A.B"
function lib.chainText(node)
	if node.tag == "global" then
		return node.name.text
	elseif node.tag == "local" then
		return node.token.text
	elseif node.tag == "indexname" then
		local head = lib.chainText(node.expression)
		if head == nil then
			return nil
		end
		return head .. node.accessor.text .. node.index.text
	end
	return nil
end

return lib
