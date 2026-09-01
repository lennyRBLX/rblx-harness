-- fix_pass — the style_assess --fix transform: WRIT14 table padding, WRIT12
-- vertical rhythm, BC5 tabs. One coordinated pass because WRIT12 and the tabs
-- clause rewrite the same leading-trivia runs, and WRIT14 needs up to three edits
-- per table — neither is safe under --auto-fix's no-overlap assumption.
--
-- Usage: lute run fix_pass.luau <in> <out>
--
-- Idempotence is proven in-process: the whole pipeline runs twice and the
-- second pass must be a byte no-op. The CST round-trip proves no semantic
-- node moved: the non-trivia token streams of input and output must be
-- identical. Any assert failing means nothing is written.
local fs = require("@std/fs")
local syntax = require("@std/syntax")
local visitor = require("@std/syntax/visitor")

local KEYWORD_CLOSERS = { ["end"] = true, ["else"] = true, ["elseif"] = true, ["until"] = true, ["}"] = true }

local changedIds = {}

local function mark(id)
	changedIds[id] = true
end

local function tokenStream(root)
	-- separator commas excluded: WRIT14 removes a trailing comma, the one
	-- token-level edit the formatter is allowed. Everything else must match.
	local out = {}
	local v = visitor.create()
	v.visitToken = function(token)
		if token.text ~= "" and token.text ~= "," then
			table.insert(out, token.text)
		end
		return true
	end
	visitor.visitBlock(root, v)
	return out
end

-- lines whose bytes may not be touched: any line intersecting a multi-line
-- string, interpolated string, or block comment
local function protectedLines(parseresult)
	local protected = {}
	local function protectSpan(location)
		if location.endLine > location.beginLine then
			-- Leading whitespace on the opening line is trivia outside the
			-- literal/comment and can be normalized safely.  Continuation
			-- lines are token bytes and must remain byte-exact.
			for line = location.beginLine + 1, location.endLine do
				protected[line] = true
			end
		end
	end
	local v = visitor.create()
	v.visitToken = function(token)
		for _, t in token.leadingTrivia do
			if t.tag == "blockcomment" then
				protectSpan(t.location)
			end
		end
		for _, t in token.trailingTrivia do
			if t.tag == "blockcomment" then
				protectSpan(t.location)
			end
		end
		protectSpan(token.location)
		return true
	end
	visitor.visitBlock(parseresult.root, v)
	return protected
end

local function splitLines(text)
	local lines = {}
	for line in (text .. "\n"):gmatch("(.-)\n") do
		table.insert(lines, line)
	end
	return lines
end

-- ---------------------------------------------------------------- WRIT14 --
-- all table constructors: no comma on the last entry. Single-line tables also
-- have one space inside each brace, while an empty table is {}. Edits are
-- edge-only spans so nested constructors stay independent; applied
-- right-to-left.
local function pass_writ14(text)
	local parsed = syntax.parse(text)
	local lines = splitLines(text)
	local edits = {} -- { line, from, to, replacement } columns 1-based, to exclusive

	local v = visitor.create()
	v.visitExprTable = function(node)
		local last = node.entries[#node.entries]
		if last ~= nil then
			local sep = last.separator
			if sep ~= nil and sep.text == "," then
				table.insert(edits, {
					line = sep.location.beginLine,
					from = sep.location.beginColumn,
					to = sep.location.endColumn,
					replacement = "",
				})
			end
		end
		if node.location.beginLine ~= node.location.endLine then
			return true
		end
		local line = node.location.beginLine
		local openEnd = node.openBrace.location.endColumn
		local closeBegin = node.closeBrace.location.beginColumn
		local inner = lines[line]:sub(openEnd, closeBegin - 1)
		if #node.entries == 0 then
			if inner:match("^%s*$") and inner ~= "" then
				table.insert(edits, { line = line, from = openEnd, to = closeBegin, replacement = "" })
			end
			return true
		end
		-- leading edge: exactly one space after {
		local lead = inner:match("^%s*") or ""
		if lead ~= " " then
			table.insert(edits, { line = line, from = openEnd, to = openEnd + #lead, replacement = " " })
		end
		-- trailing edge: exactly one space before }
		local trail = inner:match("%s*$") or ""
		if trail ~= " " then
			local trailBegin = closeBegin - #trail
			table.insert(edits, { line = line, from = trailBegin, to = closeBegin, replacement = " " })
		end
		return true
	end
	visitor.visitBlock(parsed.root, v)

	if #edits == 0 then
		return text
	end
	table.sort(edits, function(a, b)
		if a.line ~= b.line then
			return a.line > b.line
		end
		return a.from > b.from
	end)
	for _, e in edits do
		local s = lines[e.line]
		lines[e.line] = s:sub(1, e.from - 1) .. e.replacement .. s:sub(e.to)
	end
	mark("WRIT14")
	return table.concat(lines, "\n")
end

-- ---------------------------------------------------------------- WRIT12 --
-- structural blank-line ops that need the CST: a blank line after a block
-- guard clause when code follows, never after an inlined guard, one blank
-- line between sibling functions.
local function isGuardIf(stat)
	if stat.tag ~= "conditional" or stat.elseBlock ~= nil or #stat.elseifs > 0 then
		return false
	end
	local body = stat.thenBlock.statements
	local last = body[#body]
	return last ~= nil and (last.tag == "return" or last.tag == "break" or last.tag == "continue")
end

local function pass_writ12_structural(text)
	local parsed = syntax.parse(text)
	local lines = splitLines(text)
	local inserts = {} -- after line n
	local removals = {} -- line n removed (must be blank)

	local function blank(n)
		return lines[n] ~= nil and lines[n]:match("^%s*$") ~= nil
	end

	local v = visitor.create()
	v.visitStatBlock = function(block)
		for i, stat in block.statements do
			local nxt = block.statements[i + 1]
			if stat.tag == "conditional" and isGuardIf(stat) and nxt ~= nil then
				local inlined = stat.location.beginLine == stat.location.endLine
				if inlined then
					-- never a blank after an inlined guard
					local line = stat.location.endLine + 1
					while blank(line) and line < nxt.location.beginLine do
						removals[line] = true
						line += 1
					end
				elseif nxt.location.beginLine == stat.location.endLine + 1 then
					inserts[stat.location.endLine] = true
				end
			end
			local isFn = stat.tag == "function" or stat.tag == "localfunction"
			local nxtFn = nxt ~= nil and (nxt.tag == "function" or nxt.tag == "localfunction")
			if isFn and nxtFn and nxt.location.beginLine == stat.location.endLine + 1 then
				inserts[stat.location.endLine] = true
			end
		end
		return true
	end
	visitor.visitBlock(parsed.root, v)

	if next(inserts) == nil and next(removals) == nil then
		return text
	end
	local out = {}
	for n, line in lines do
		if not removals[n] then
			table.insert(out, line)
		end
		if inserts[n] then
			table.insert(out, "")
		end
	end
	mark("WRIT12")
	return table.concat(out, "\n")
end

-- ------------------------------------------------- text sweep: WRIT12+BC5 --
-- collapse 2+ blank lines to 1, strip blanks before end/else/elseif/until,
-- convert leading spaces to tabs. One top-down sweep with fresh protection.
local function leadingUnit(lines, protected)
	local minRun = nil
	for n, line in lines do
		if not protected[n] then
			local indent = line:match("^([ \t]+)%S")
			if indent ~= nil then
				local _, spaces = indent:gsub(" ", "")
				if spaces > 0 then
					minRun = if minRun == nil then spaces else math.min(minRun, spaces)
				end
			end
		end
	end
	if minRun == 2 then
		return 2
	end
	return 4
end

local function pass_sweep(text)
	local parsed = syntax.parse(text)
	local protected = protectedLines(parsed)
	local lines = splitLines(text)
	local unit = leadingUnit(lines, protected)
	local out = {}
	local pendingBlanks = 0
	local sawContent = false

	local function flushBlanks(nextLine, nextProtected)
		if pendingBlanks > 0 then
			local closer = false
			if nextLine ~= nil and not nextProtected then
				local word = nextLine:match("^%s*(%S+)")
				closer = word ~= nil and KEYWORD_CLOSERS[word] == true
			end
			if closer or not sawContent or nextLine == nil then
				if pendingBlanks > 0 then
					mark("WRIT12")
				end
			else
				table.insert(out, "")
				if pendingBlanks > 1 then
					mark("WRIT12")
				end
			end
			pendingBlanks = 0
		end
	end

	for n, line in lines do
		if protected[n] then
			flushBlanks(line, true)
			table.insert(out, line)
			sawContent = true
		elseif line:match("^%s*$") then
			if line ~= "" then
				mark("WRIT12") -- whitespace-only line normalizes to empty
			end
			pendingBlanks += 1
		else
			flushBlanks(line, false)
			local lead, rest = line:match("^([ \t]+)(.*)$")
			if lead ~= nil and lead:find(" ", 1, true) ~= nil then
				local _, spaces = lead:gsub(" ", "")
				local _, tabs = lead:gsub("\t", "")
				local levels = tabs + math.ceil(spaces / unit)
				line = string.rep("\t", levels) .. rest
				mark("BC5")
			end
			table.insert(out, line)
			sawContent = true
		end
	end
	flushBlanks(nil, false)
	return table.concat(out, "\n")
end

local function pipeline(text)
	local result = pass_writ14(text)
	result = pass_writ12_structural(result)
	result = pass_sweep(result)
	-- exactly one trailing newline
	result = result:gsub("\n*$", "") .. "\n"
	return result
end

local function assertTabIndentation(text)
	local parsed = syntax.parse(text)
	local protected = protectedLines(parsed)
	for n, line in splitLines(text) do
		if not protected[n] then
			local indent = line:match("^([ \t]+)%S")
			assert(indent == nil or not indent:find(" ", 1, true), "fix_pass: BC5 indentation repair remained on line " .. n)
		end
	end
end

local ARGS = { ... } -- lute run passes { scriptPath, arg1, arg2, ... }

local function main()
	local inPath, outPath = ARGS[2], ARGS[3]
	assert(inPath ~= nil and outPath ~= nil, "usage: lute run fix_pass.luau <in> <out>")
	local source = fs.readFileToString(inPath)

	local before = syntax.parse(source)
	local streamBefore = tokenStream(before.root)

	local once = pipeline(source)
	assertTabIndentation(once)
	local after = syntax.parse(once) -- parse-verify: an unparseable result never lands
	local streamAfter = tokenStream(after.root)

	assert(#streamBefore == #streamAfter, "fix_pass: token count changed - refusing to write")
	for i, tok in streamBefore do
		assert(streamAfter[i] == tok, "fix_pass: token " .. i .. " changed (" .. tok .. " -> " .. tostring(streamAfter[i]) .. ") - refusing to write")
	end

	local twice = pipeline(once)
	assert(twice == once, "fix_pass: second pass is not a byte no-op - refusing to write")

	fs.writeStringToFile(outPath, once)
	if once == source or next(changedIds) == nil then
		print("clean")
	else
		local ids = {}
		for id in changedIds do
			table.insert(ids, id)
		end
		table.sort(ids)
		print("changed|" .. table.concat(ids, ","))
	end
end

main()
