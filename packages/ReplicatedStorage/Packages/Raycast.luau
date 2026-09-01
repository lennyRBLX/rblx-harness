--[[
Raycast:
	Manages anything related to ray's, raycasting, and finding
	objects with rays.
]]

local DEFAULT_DISTANCE = 1000

local UserInputService = game:GetService("UserInputService")
local GuiService = game:GetService("GuiService")
local CurrentCamera = workspace.CurrentCamera

local m = {}

function m:Visualize(from, to)
	assert(typeof(from) == "CFrame", "Raycast.Visualize | from must be a matrix")
	assert(type(to) == "number" or typeof(to) == "Vector3", "Raycast.Visuaize | to must be a number, representing distance, or a vector")

	local target, distance = Vector3.zero, 0
	if type(to) == "number" then
		target = from * (from.LookVector * to)
		distance = to
	else
		target = to
		distance = (from.Position - to).Magnitude
	end

	local new = Instance.new("Part")
	new.Size = Vector3.new(distance, 0.75, 0.75)
	new.Transparency = 0.6
	new.Anchored = true
	new.CFrame = CFrame.lookAt(from.Position:Lerp(target, 0.5), target) * CFrame.Angles(0, math.rad(90), 0)
	new.Material = Enum.Material.Neon
	new.Shape = Enum.PartType.Cylinder
	new.CanCollide = false
	new.Parent = workspace.Terrain

	--task.delay(5, new.Destroy, new)
end

function m:Cast(from, to, params)
	assert(typeof(from) == "CFrame", "Raycast.Cast | from must be a matrix")
	assert(type(to) == "number" or typeof(to) == "Vector3", "Raycast.Cast | to must be a number, representing distance, or a vector")
	assert(typeof(params) == "RaycastParams", "Raycast.Cast | params must be raycast parameters")
	
	local direction = Vector3.zero
	if type(to) == "number" then
		direction = from.LookVector * to
	else
		local lookAt = CFrame.new(from.Position, to)
		direction = lookAt.LookVector * (from.Position - to).Magnitude
	end
	
	return workspace:Raycast(from.Position, direction, params)
end

function m:CastTowards(from, direction, params)
	assert(typeof(from) == "CFrame", "Raycast.CastTowards | from must be a matrix")
	assert(typeof(direction) == "Vector3", "Raycast.CastTowards | direction must be a vector")
	assert(typeof(params) == "RaycastParams", "Raycast.CastTowards | params must be raycast parameters")
	
	return workspace:Raycast(from.Position, direction, params)
end

function m:CastAtMouse(params, distance)
	assert(typeof(params) == "RaycastParams", "Raycast.CastTowards | params must be raycast parameters")
	
	distance = tonumber(distance) or DEFAULT_DISTANCE
	
	local mouseLocation, guiInset = UserInputService:GetMouseLocation(), GuiService:GetGuiInset()
	local ray = CurrentCamera:ScreenPointToRay(mouseLocation.X + guiInset.X, mouseLocation.Y - guiInset.Y)
	
	return workspace:Raycast(ray.Origin, ray.Direction * distance, params)
end

function m:CastWithIgnoreList(from, to, ignored)
	assert(typeof(from) == "CFrame", "Raycast.CastWithIgnoreList | from must be a matrix")
	assert(type(to) == "number" or typeof(to) == "Vector3", "Raycast.CastWithIgnoreList | to must be a number, representing distance, or a vector")
	assert(typeof(ignored) == "table", "Raycast.CastWithIgnoreList | ignored must be a table")
	
	local params = RaycastParams.new()
	params.FilterDescendantsInstances = ignored
	params.FilterType = Enum.RaycastFilterType.Exclude
	
	return self:Cast(from, to, params)
end

function m:CastWithWhiteList(from, to, whitelist)
	assert(typeof(from) == "CFrame", "Raycast.CastWithWhiteList | from must be a matrix")
	assert(type(to) == "number" or typeof(to) == "Vector3", "Raycast.CastWithWhiteList | to must be a number, representing distance, or a vector")
	assert(typeof(whitelist) == "table", "Raycast.CastWithWhiteList | whitelist must be a table")
	
	local params = RaycastParams.new()
	params.FilterDescendantsInstances = whitelist
	params.FilterType = Enum.RaycastFilterType.Include
	
	return self:Cast(from, to, params)
end

function m:CastTowardsWithIgnoreList(from, direction, ignored)
	assert(typeof(from) == "CFrame", "Raycast.CastTowardsWithIgnoreList | from must be a matrix")
	assert(typeof(direction) == "Vector3", "Raycast.CastTowardsWithIgnoreList | direction must be a vector")
	assert(typeof(ignored) == "table", "Raycast.CastTowardsWithIgnoreList | ignored must be a table")
	
	local params = RaycastParams.new()
	params.FilterDescendantsInstances = ignored
	params.FilterType = Enum.RaycastFilterType.Exclude
	
	return self:CastTowards(from, direction, params)
end

function m:CastTowardsWithWhiteList(from, direction, whitelist)
	assert(typeof(from) == "CFrame", "Raycast.CastWithWhiteList | from must be a matrix")
	assert(typeof(direction) == "Vector3", "Raycast.CastWithWhiteList | direction must be a vector")
	assert(typeof(whitelist) == "table", "Raycast.CastWithWhiteList | whitelist must be a table")
	
	local params = RaycastParams.new()
	params.FilterDescendantsInstances = whitelist
	params.FilterType = Enum.RaycastFilterType.Include
	
	return self:CastTowards(from, direction, params)
end

return m
