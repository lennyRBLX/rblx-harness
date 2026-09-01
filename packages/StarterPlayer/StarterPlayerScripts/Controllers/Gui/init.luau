--[[
Gui:
	Owns the interface tree. Each direct child module is one GUI controller
	exposing Start; they are loaded here and started in parallel, so a child
	that raises takes only itself down (prescribed template — stripped from
	the developer's standing stack to the child-loading core). Everything a
	single GUI needs lives in that GUI's own module.
]]

local m = {}

-- functions
function m:Start()
	for _, module in script:GetChildren() do
		if not module:IsA("ModuleScript") then
			continue
		end

		local ok, gui = pcall(require, module)
		if not ok then
			warn("ERROR WHILE REQUIRING GUI '" .. module.Name .. "'; ERROR:", gui)
			continue
		end

		if type(gui) ~= "table" or type(gui.Start) ~= "function" then
			continue
		end

		task.spawn(function()
			local started, msg = pcall(gui.Start, gui)
			if not started then
				warn("FAILED TO START GUI '" .. module.Name .. "'; ERROR:", msg)
			end
		end)
	end
end

return m
