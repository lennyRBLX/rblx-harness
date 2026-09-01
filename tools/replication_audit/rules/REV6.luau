-- REV6: the four sins, one rule with four clauses.
--   1 workspace-attribute used as a channel                      (lean)
--   2 FireAllClients payload derived from retained module state  (lean)
--   3 Signal across the server/client boundary                   (lean)
--   4 table argument to a remote                                 (guarantee
--     for a table constructor, lean for an identifier)
-- The check cites REV6, never BC2 — BC2 states the channels and stays prose.
local visitor = require("@std/syntax/visitor")
local lib = require("../lib")

local name = "REV6"

local FIRES = { FireAllClients = true, FireClient = true, FireServer = true, InvokeClient = true, InvokeServer = true }

local function lint(ast, sourcepath, context)
	local out = {}
	local moduleLocals = lib.moduleLocals(ast)
	local requires = lib.resolveBindings(ast)

	-- locals initialized from Signal.new() / <SignalPkg>.new()
	local signalLocals = {}
	for decl, init in moduleLocals do
		if init and init.tag == "call" then
			local f = init.func
			if f.tag == "indexname" and f.index.text == "new" then
				local root = lib.chainText(f.expression)
				if root ~= nil then
					for reqDecl, chain in requires do
						if root == reqDecl.name.text and chain:find("Signal", 1, true) then
							signalLocals[decl] = true
						end
					end
				end
			end
		end
	end

	local function isModuleState(arg)
		if arg.tag == "local" then
			return moduleLocals[arg["local"]] ~= nil, arg["local"]
		elseif arg.tag == "indexname" then
			local root = arg.expression
			while root.tag == "indexname" do
				root = root.expression
			end
			if root.tag == "local" then
				local decl = root["local"]
				if moduleLocals[decl] ~= nil then
					return true, decl
				end
				-- m.X where m is the module table
				local init = moduleLocals[decl]
				if init and init.tag == "table" then
					return true, decl
				end
			end
		end
		return false, nil
	end

	local v = visitor.create()
	v.visitExprCall = function(node)
		local method, f = lib.methodCall(node)
		if method == nil then
			return true
		end
		-- sin 1: workspace-attribute as a channel
		if (method == "SetAttribute" or method == "GetAttributeChangedSignal") then
			local chain = lib.chainText(f.expression)
			if chain ~= nil and (chain == "workspace" or chain:match("^workspace[.:]")) then
				table.insert(
					out,
					lib.violation(name, node.location, chain .. ":" .. method, "Use a Folder + ValueObjects, not a Workspace attr; retry.", sourcepath)
				)
			end
		end
		if not FIRES[method] then
			return true
		end
		local args = lib.nodes(node.arguments)
		local start = (method == "FireClient" or method == "InvokeClient") and 2 or 1
		for i = start, #args do
			local arg = args[i]
			-- sin 4: table through a remote
			if arg.tag == "table" then
				table.insert(
					out,
					lib.violation(name, arg.location, method .. " table constructor", "Store state in Exclusive / Folder + ValueObjects; send only the event; retry.", sourcepath)
				)
			else
				local isState, decl = isModuleState(arg)
				if isState and decl ~= nil and signalLocals[decl] then
					-- sin 3: Signal across the boundary
					table.insert(
						out,
						lib.violation(name, arg.location, "Signal through " .. method, "Keep Signal in 1 layer; use a remote event across layers; retry.", sourcepath)
					)
				elseif isState and method == "FireAllClients" then
					-- sin 2: payload outliving the fire — late joiners get nothing
					local init = decl and moduleLocals[decl]
					if arg.tag == "indexname" or (init and init.tag == "table") then
						table.insert(
							out,
							lib.violation(name, arg.location, method .. " payload from retained module state", "Store retained state in replicated instances for late joiners; retry.", sourcepath)
						)
					end
				elseif arg.tag == "local" then
					local init = moduleLocals[arg["local"]]
					if init and init.tag == "table" then
						table.insert(
							out,
							lib.violation(name, arg.location, method .. " table " .. arg.token.text, "Store state in Exclusive / Folder + ValueObjects; retry.", sourcepath)
						)
					end
				end
			end
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return table.freeze({ name = name, lint = lint })
