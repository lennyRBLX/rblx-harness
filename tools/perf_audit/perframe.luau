-- per-frame context resolution shared by the perf_audit rules: a literal
-- RunService.Heartbeat/Stepped/RenderStepped:Connect body, or m:Start /
-- m:step. Anything else is not a per-frame context and is skipped.
local visitor = require("@std/syntax/visitor")

local perframe = {}

local FRAME_EVENTS = { Heartbeat = true, Stepped = true, RenderStepped = true, PreRender = true, PreSimulation = true, PostSimulation = true }

function perframe.bodies(ast)
	local out = {}
	local v = visitor.create()
	v.visitExprCall = function(node)
		local f = node.func
		if f.tag == "indexname" and (f.index.text == "Connect" or f.index.text == "ConnectParallel") then
			local ev = f.expression
			if ev.tag == "indexname" and FRAME_EVENTS[ev.index.text] then
				for _, pair in node.arguments do
					if pair.node.tag == "function" then
						table.insert(out, pair.node.body)
					end
				end
			end
		end
		return true
	end
	v.visitStatFunction = function(node)
		-- m:step is a genuine per-frame method; m:Start is where connections
		-- are REGISTERED — its own body is the once-only place hoists belong,
		-- so it is not collected
		local fname = node.name
		if fname.tag == "indexname" and fname.index.text == "step" then
			table.insert(out, node.func.body)
		end
		return true
	end
	visitor.visitBlock(ast, v)
	return out
end

return perframe
