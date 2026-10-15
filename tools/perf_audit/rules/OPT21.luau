-- Representation candidates only. No cardinality, frequency, or timing inference.
local visitor = require("@std/syntax/visitor")
local lib = require("../../replication_audit/lib")
local name = "OPT21"

local codecs = {
	JSONEncode = true, JSONDecode = true,
	CompressBuffer = true, DecompressBuffer = true,
	ComputeBufferHash = true, ComputeStringHash = true,
}

local function lint(ast, sourcepath, context)
	local out = {}
	local function note(node, subject, action)
		table.insert(out, lib.violation(name, node.location, subject .. " candidate", action .. "; size/frequency/phase and measured benefit unknown", sourcepath))
	end
	local v = visitor.create()
	v.visitExprCall = function(node)
		local f = node.func
		if f.tag ~= "indexname" then return true end
		local owner = if f.expression.tag == "global" then f.expression.name.text else nil
		local member = f.index.text
		if owner == "table" and member == "find" then
			note(node, "linear search", "Require hit/miss and reuse inputs; compare scan with direct/indexed lookup including construction and updates")
		elseif owner == "table" and member == "sort" then
			local costly = false
			local comparator = lib.nodes(node.arguments)[2]
			if comparator and comparator.tag == "function" then
				local cv = visitor.create()
				cv.visitExprFunction = function() return false end
				cv.visitExprCall = function() costly = true return true end
				visitor.visitBlock(comparator.body, cv)
			end
			note(node, if costly then "sort with comparator calls" else "full sort",
				if costly then "Require result count and update rate; compare cached sort keys including extraction and maintenance"
				else "Require result count and update rate; compare full sort, maintained order, and bounded selection")
		elseif (owner == "buffer" and (member == "fromstring" or member == "tostring"))
			or (owner == "string" and (member == "pack" or member == "unpack"))
			or (f.accessor.text == ":" and codecs[member]) then
			note(node, "encoding/hash/conversion call", "Require receiver and consuming path; measure codec CPU, copies/peak memory, and actual persisted/transmitted bytes")
		end
		return true
	end
	v.visitExprIndexExpr = function(node)
		local key = node.index
		if key.tag == "call" or (key.tag == "binary" and key.operator.text == "..") then
			note(key, "computed lookup key", "Require identity/lifetime and reuse; compare cached keys, dense IDs, or collision-safe hashes including key construction")
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
