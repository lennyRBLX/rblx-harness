local DEFAULT_PROPERTIES = {
	BasePart = { "Color" },
	ImageLabel = { "ImageColor3" },
	ImageButton = { "ImageColor3" },
	TextLabel = { "TextColor3" },
	TextButton = { "TextColor3" },
	Frame = { "BackgroundColor3" }
}

local RunService = game:GetService("RunService")

local m = {
	Initialized = false,
	Testers = {},
	List = nil
}

-- functions
function m:Get(speed: number?, saturation: number?, value: number?, syncedToServer: boolean?)
	speed = speed or 10
	saturation = saturation or 1
	value = value or 1
	
	local t = (syncedToServer and workspace:GetServerTimeNow()) or tick()
	return Color3.fromHSV((t % speed) / speed, saturation, value)
end

function m:Remove(object: BasePart | ImageLabel | ImageButton | TextLabel | TextButton | Frame | (color: Color3) -> nil, resetProperties: boolean?)
	local info = self.List[object]
	if not info then
		return
	end
	
	self.List[object] = nil
	
	if resetProperties and typeof(object) == "Instance" then
		for property, value in pairs(info[6]) do
			object[property] = value
		end
	end
	
	if info[7] then
		info[7]:Disconnect()
	end
end

function m:Add(object: BasePart | ImageLabel | ImageButton | TextLabel | TextButton | Frame | (color: Color3) -> nil, properties: { [number]: string }?, speed: number?, saturation: number?, value: number?, syncedToServer: boolean?)
	local defaults, destroying = nil, nil
	if typeof(object) == "function" then
		if not pcall(function() object(Color3.new()) end) then
			return false
		end
		
		properties = nil
	else
		local tester = nil
		for className, p in pairs(DEFAULT_PROPERTIES) do
			if object:IsA(className) then
				tester = self.Testers[className]
				properties = properties or p
				break
			end
		end
		
		if not properties or not tester then
			return false
		end
		
		defaults = {}
		
		for _, property in pairs(properties) do
			if not pcall(function() tester[property] = Color3.new() end) then
				return false
			end
			
			defaults[property] = object[property]
		end
		
		destroying = object.Destroying:Connect(function()
			self:Remove(object)
		end)
	end
	
	self.List[object] = {
		properties,
		speed or 10,
		saturation or 1,
		value or 1,
		syncedToServer,
		defaults,
		destroying
	}
end

function m:Init()
	if self.Initialized then
		return self
	end
	
	self.Initialized = true
	
	for name, _ in pairs(DEFAULT_PROPERTIES) do
		local instance = name
		if name == "BasePart" then
			instance = "Part"
		end
		
		self.Testers[name] = Instance.new(instance)
	end
	
	local list = {}
	self.List = list
	
	RunService:BindToRenderStep("Rainbow.Loop", Enum.RenderPriority.Camera.Value + 1, function(step)
		local localTick, serverTick = tick(), workspace:GetServerTimeNow()
		for object, info in list do -- done w/o locals for performance
			local t = info[5] and serverTick or localTick
			
			local color = Color3.fromHSV((t % info[2]) / info[2], info[3], info[4])
			if not info[1] then
				object(color)
			else
				for _, property in info[1] do
					object[property] = color
				end
			end
		end
	end)
	
	return self
end

return m