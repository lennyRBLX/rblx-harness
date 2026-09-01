--[[
Updates:
	Client half of the content-drop lifecycle (KNOWLEDGE_BASIS §3.6). Each
	direct child module mirrors a server update: Start(silent) layers in
	client-side content, Destroy tears the featured layer down. The server
	replicates the started/featured set as BoolValues under
	ReplicatedStorage.Updates (true = featured, false = content only).
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local m = {
	Ran = false,

	__modules = {},

	Started = {},
	Active = {}
}

local stateFolder = nil

-- privates
function m:update()
	for name, s in pairs(self.__modules) do
		local state = stateFolder:FindFirstChild(name)
		if not state then
			continue
		end

		if not self.Started[name] then
			local success, msg = pcall(s.Start, s, not state.Value)
			if not success then
				warn("FAILED TO START CLIENT UPDATE '" .. name .. "'; ERROR:", msg)
			end

			self.Started[name] = true
			self.Active[name] = state.Value
		elseif self.Active[name] and not state.Value then
			local success, msg = pcall(s.Destroy, s)
			if not success then
				warn("FAILED TO DESTROY CLIENT UPDATE '" .. name .. "'; ERROR:", msg)
			end

			self.Active[name] = false
		end
	end
end

-- functions
function m:IsActive(name)
	return self.Active[name] == true
end

function m:Start()
	stateFolder = ReplicatedStorage:WaitForChild("Updates")

	for _, module in pairs(script:GetChildren()) do
		local e, msg = pcall(require, module)
		if not e then
			warn("ERROR WHILE REQUIRING CLIENT UPDATE '" .. module.Name .. "'; ERROR:", msg)
			continue
		elseif not msg.Destroy then
			warn("CLIENT UPDATE '" .. module.Name .. "' MISSING :Destroy")
		end

		self.__modules[module.Name] = msg
	end

	-- setup | state
	local function watch(state)
		state:GetPropertyChangedSignal("Value"):Connect(function()
			self:update()
		end)
	end

	for _, state in pairs(stateFolder:GetChildren()) do
		watch(state)
	end

	stateFolder.ChildAdded:Connect(function(state)
		watch(state)
		self:update()
	end)

	self:update()
	self.Ran = true
end

return m
