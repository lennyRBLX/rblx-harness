--[[
Ground:
	Gives API to get the potential ground objects in the map.
]]

local m = {
	Initialized = false,
	Cache = { workspace.Terrain }
}

local CACHE = m.Cache

-- private
function m.add(part)
	if part:IsA("BasePart") and (part.CanCollide ~= false and part.Transparency ~= 1) then
		table.insert(CACHE, part)
	end
end

function m.remove(obj)
	-- single locate
	local index = table.find(CACHE, obj)
	if index then
		table.remove(CACHE, index)
	end
	
	-- NOTE: split to increase speed, but trading off bytecode size

	if obj.Parent then -- path compare
		for _, o in pairs(CACHE) do
			if o:IsDescendantOf(obj) or obj:IsDescendantOf(o) then
				local i = table.find(CACHE, o)
				if i then
					table.remove(CACHE, i)
					m.Removed:Fire(o)
				end
			end
		end
	else -- nil removal
		for _, o in pairs(CACHE) do
			if not o.Parent then
				local i = table.find(CACHE, o)
				if i then
					table.remove(CACHE, i)
					m.Removed:Fire(o)
				end
			end
		end
	end
end

-- functions
function m:Get()
	if not self.Initialized then
		self:Init()
	end

	return CACHE
end

function m:Init()
	if self.Initialized then
		return self
	end
	
	self.Initialized = true
	
	local map = workspace:FindFirstChild("Map")
	if map then
		for _, o in pairs(map:GetDescendants()) do
			self.add(o)
		end
	end

	workspace.ChildAdded:Connect(function(obj)
		if obj.Name == "Map" then
			for _, o in pairs(obj:GetDescendants()) do
				self.add(o)
			end
		end
	end)
	
	workspace.ChildRemoved:Connect(self.remove)
	
	return self
end

function m:Refresh()
	table.clear(self.Cache)
	
	self.Initialized = false
	self:Init()
end

return m
