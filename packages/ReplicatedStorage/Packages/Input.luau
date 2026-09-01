--[[
Input:
	Module designed to allow easy binding of keyboard, gamepad, and touch device input methods.
	This module is also designed to be able to communicate a necessary GUI update via .DeviceChange
	when the input device changes.
	
Example:
	
	local Input = require(game.ReplicatedStorage.Modules.Input)
	
	Input:Map("Sprint", {
		Enum.KeyCode.LShift, -- when the player presses the left shift key
		Enum.KeyCode.Thumbstick1 -- when the player presses down on left thumbstick
	}, {
		"TouchStarted",
		"TouchMoved"
	}, {
		"Wheel"
	}, false)
	
	function activateSprint()
	end
	
	function deactivateSprint()
	end
	
	-- keyboard / xbox support
	Input:Bind("Sprint", function(input, state, gameProcessed)
		if state == Enum.UserInputState.End or state == Enum.UserInputState.Cancel then
			deactivateSprint()
		elseif state == Enum.UserInputState.Begin then
			activateSprint()
		end
	end)
	
	-- touch / mobile support
	local startedPos = Vector3.new()
	Input:BindTouch("Sprint", "TouchStarted", function(touch, processed)
		startedPos = touch.Position
	end)
	
	Input:BindTouch("Sprint", "TouchMoved", function(touch, processed)
		if (touch.Position - startedPos).Magnitude > 10 then
			activateSprint()
		end
	end)
	
	-- mouse inputs example
	local startWheel = 0
	Input:BindMouse("Sprint", "Wheel", function(input, processed)
		if state == Enum.UserInputState.Start then
			startWheel = tick()
		elseif state == Enum.UserInputState.Change and tick() - startWheel > 1 then
			activateSprint()
		elseif state == Enum.UserInputState.End or state == Enum.UserInputState.Cancel then
			startWheel = 0
			deactivateSprint()
		end
	end)
]]

local PHONE_ASPECT_RATIOS = {
	NumberRange.new(0.42, 0.48), -- 21:9 portrait (0.429) - Ultra-wide phones
	NumberRange.new(0.46, 0.50), -- 20:9 portrait (0.45) - Modern Android phones
	NumberRange.new(0.51, 0.57), -- 19.5:9 portrait (0.462) - iPhone 11, 12, 13, 14
	NumberRange.new(0.54, 0.58), -- 18:9 portrait (0.5) - Common Android
	NumberRange.new(0.56, 0.64), -- 16:9 portrait (0.5625) - Older phones
	NumberRange.new(1.75, 1.87), -- 16:9 landscape (1.778)
	NumberRange.new(1.95, 2.05), -- 20:9 landscape (2.0)
	NumberRange.new(2.08, 2.18) -- 21:9 landscape (2.333)
}

local PREFERRED_INPUT_NAMES = {
	[Enum.PreferredInput.KeyboardAndMouse] = "Keyboard",
	[Enum.PreferredInput.Gamepad] = "Gamepad",
	[Enum.PreferredInput.Touch] = "Touch",
}

local ContextActionService = game:GetService("ContextActionService")
local GuiService = game:GetService("GuiService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local CurrentCamera = workspace.CurrentCamera

local Signal = require(ReplicatedStorage.Packages.Signal)

local m = {
	MappedInputs = {},
	InputButtons = {},
	InputType = "",
	IsTablet = false,
	DeviceChanged = Signal.new(),
	Initialized = false
}

function m:Map(name, inputs, touchInputs, mouseInputs, hasTouch)
	assert(typeof(name) == "string", "Input.Map | name must be a string")
	assert(typeof(inputs) == "table" or typeof(touchInputs) == "table" or typeof(mouseInputs) == "table", "Input.Map | inputs, touchInputs, or mouseInputs must be a table to map correctly")
	
	self:Init()
	
	hasTouch = typeof(hasTouch) == "boolean" and hasTouch or false
	
	if self:IsMapped(name) then
		self:UnbindAll(name)
	end
	
	local mappedInput = {
		HasTouch = hasTouch,
		Inputs = {},
		TouchInputs = {},
		MouseInputs = {},
		Handled = false
	}
	
	self.MappedInputs[name] = mappedInput
	
	if inputs then
		for _, key in pairs(inputs) do
			mappedInput.Inputs[key] = {}
		end
	end
	
	if touchInputs then
		for _, key in pairs(touchInputs) do
			mappedInput.TouchInputs[key] = {}
		end
	end
	
	if mouseInputs then
		for _, key in pairs(mouseInputs) do
			mappedInput.MouseInputs[key] = {}
		end
	end
end

function m:Unmap(name)
	assert(typeof(name) == "string", "Input.Map | name must be a string")
	
	self:Init()
	
	if not self.MappedInputs[name] then
		return
	end

	self:UnbindAll(name)
	self.MappedInputs[name] = nil
end

function m:IsMapped(name)
	return self.MappedInputs[tostring(name)] ~= nil
end

m.handleBinds = function(actionName, inputState, inputObject)
	if m:IsMapped(actionName) then
		-- Respect the Icon (topbar) gamepad Selection mode. While a topbar icon is
		-- selected via the gamepad, its KeyCodes belong to the topbar -- DPad navigates
		-- between icons, ButtonA opens, ButtonB backs out (handled by the Icon package
		-- and GuiService navigation). Deny our KeyCode callbacks so world binds don't
		-- leak (e.g. ButtonB -> crouch, DPadLeft/Right -> tools) while the player is
		-- driving the topbar. We return Pass (nil) rather than Sink so the input still
		-- reaches GuiService and topbar navigation keeps working.
		if m.InputType == "Gamepad" then
			local selected = GuiService.SelectedObject
			if selected and selected:GetAttribute("CorrespondingIconUID") then
				return
			end
		end

		local mappedInput = m.MappedInputs[actionName]
		
		-- send input
		local methods = mappedInput.Inputs[inputObject.KeyCode]
		if methods then
			local gameProcessed = false
			for _, f in pairs(methods) do
				local result = f(inputObject, inputState, gameProcessed)
				if result == true then
					gameProcessed = true
				end
			end
		end
	end
end

function m:Bind(name, f)
	assert(self:IsMapped(name), "Input.Bind | name must be mapped before binding to a function")
	assert(typeof(f) == "function", "Input.Bind | f must be a function")
	
	local mappedInput = self.MappedInputs[name]
	local inputs = mappedInput.Inputs
	
	for keyCode, methods in pairs(inputs) do
		methods[#methods + 1] = f
	end

	if not mappedInput.Handled then
		mappedInput.Handled = true
		
		local supportedInputs = {}
		for keyCode, methods in pairs(mappedInput.Inputs) do
			if typeof(keyCode) ~= "string" then
				supportedInputs[#supportedInputs + 1] = keyCode
			end
		end

		ContextActionService:BindAction(name, self.handleBinds, mappedInput.HasTouch, table.unpack(supportedInputs))
	end
end

function m:BindTouch(name, eventName, f)
	assert(self:IsMapped(name), "Input.BindTouch | name must be mapped before binding to a function")
	assert(typeof(eventName) == "string", "Input.BindTouch | eventName must be a string")
	assert(typeof(f) == "function", "Input.BindTouch | f must be a function")
	
	local mappedInput = self.MappedInputs[name]
	local methods = mappedInput.TouchInputs[eventName]
	assert(typeof(methods) == "table", "Input.BindTouch | methods is nil, events should be mapped with :Map before binding")
	
	methods[#methods + 1] = f
end

function m:BindMouse(name, eventName, f)
	assert(self:IsMapped(name), "Input.BindMouse | name must be mapped before binding to a function")
	assert(typeof(eventName) == "string", "Input.BindMouse | eventName must be a string")
	assert(typeof(f) == "function", "Input.BindMouse | f must be a function")

	local mappedInput = self.MappedInputs[name]
	local methods = mappedInput.MouseInputs[eventName]
	assert(typeof(methods) == "table", "Input.BindMouse | methods is nil, events should be mapped with :Map before binding")

	methods[#methods + 1] = f
end

function m:Unbind(name, f)
	assert(self:IsMapped(name), "Input.Unbind | name must be mapped before unbinding")
	assert(typeof(f) == "function", "Input.Unbind | f must be the function to be unbinded")
	
	local mappedInput = self.MappedInputs[name]
	local inputs = mappedInput.Inputs
	
	local result = false
	local totalMethods = 0
	for _, methods in pairs(inputs) do
		for i, method in pairs(methods) do
			if method == f then
				result = true
				table.remove(methods, i)
				break
			end
		end
		
		totalMethods += #methods
	end
	
	if #totalMethods == 0 then
		self:UnbindAll(name)
	end
	
	return result
end

function m:UnbindTouch(name, f)
	assert(self:IsMapped(name), "Input.UnbindTouch | name must be mapped before unbinding")
	assert(typeof(f) == "function", "Input.UnbindTouch | f must be a function")
	
	local mappedInput = self.MappedInputs[name]
	local inputs = mappedInput.TouchInputs
	
	local result = false
	local totalMethods = 0
	for _, methods in pairs(inputs) do
		for i, method in pairs(methods) do
			if method == f then
				result = true
				table.remove(methods, i)
				break
			end
		end

		totalMethods += #methods
	end
	
	if #totalMethods == 0 then
		self:UnbindAllTouch(name)
	end
	
	return result
end

function m:UnbindMouse(name, f)
	assert(self:IsMapped(name), "Input.UnbindMouse | name must be mapped before unbinding")
	assert(typeof(f) == "function", "Input.UnbindMouse | f must be a function")

	local mappedInput = self.MappedInputs[name]
	local inputs = mappedInput.MouseInputs

	local result = false
	local totalMethods = 0
	for _, methods in pairs(inputs) do
		for i, method in pairs(methods) do
			if method == f then
				result = true
				table.remove(methods, i)
				break
			end
		end
		
		totalMethods += #methods
	end
	
	if #totalMethods == 0 then
		self:UnbindAllMouse(name)
	end

	return result
end

function m:UnbindAll(name)
	assert(self:IsMapped(name), "Input.UnbindAll | name must be mapped before unbinding all inputs")
	
	local mappedInput = self.MappedInputs[name]
	if not mappedInput then
		return
	end

	if mappedInput.Handled then
		mappedInput.Handled = false
		ContextActionService:UnbindAction(name)
	end

	for _, methods in pairs(mappedInput.Inputs) do
		table.clear(methods)
	end

	self:UnbindAllTouch(name)
	self:UnbindAllMouse(name)
end

function m:UnbindAllTouch(name)
	assert(self:IsMapped(name), "Input.UnbindAllTouch | name must be mapped before unbinding all touch inputs")
	
	local mappedInput = self.MappedInputs[name]
	if not mappedInput then
		return
	end

	for _, methods in pairs(mappedInput.TouchInputs) do
		table.clear(methods)
	end
end

function m:UnbindAllMouse(name)
	assert(self:IsMapped(name), "Input.UnbindAllMouse | name must be mapped before unbinding all touch inputs")
	
	local mappedInput = self.MappedInputs[name]
	if not mappedInput then
		return
	end

	for _, methods in pairs(mappedInput.MouseInputs) do
		table.clear(methods)
	end
end

function m:GetTouchButton(name)
	assert(self:IsMapped(name), "Input.GetTouchButton | name must be mapped before gathering mobile input button")
	
	if not ContextActionService:GetButton(name) then
		return nil
	end
	
	local button = self.InputButtons[name]
	if not button then
		button = setmetatable({}, {
			__index = function(self, key)
				if key == "Button" then
					return ContextActionService:GetButton(rawget(self, "_actionName"))
				end
				
				return rawget(self, key)
			end,
			__newindex = function(self, name, value)				
				local actionName = rawget(self, "_actionName")
				if name == "Image" then
					ContextActionService:SetImage(actionName, value)
				elseif name == "Position" then
					ContextActionService:SetPosition(actionName, value)
				elseif name == "Title" then
					ContextActionService:SetTitle(actionName, value)
				elseif name == "Description" then
					ContextActionService:SetDescription(actionName, value)
				elseif name == "Size" then
					ContextActionService:GetButton(rawget(self, "_actionName")).Size = value
				end

				rawset(self, name, value)
			end
		})

		button._actionName = name
		self.InputButtons[name] = button
	end
	
	return button
end

function m:GetCoreTouchElement(name)
	return game:GetService("Players").LocalPlayer:WaitForChild("PlayerGui"):WaitForChild("TouchGui"):FindFirstChild(tostring(name))
end

function m:deviceChange(name)
	if self.InputType ~= name then
		-- update InputType BEFORE firing: Signal:Fire resumes handlers synchronously
		-- (task.spawn), so any consumer that reads the global Input.InputType during the
		-- handler must see the new value. Firing first left it stale (old device).
		local previous = self.InputType
		self.InputType = name
		self.DeviceChanged:Fire(name, previous)
	end
end

function m:Init()
	if self.Initialized then
		return
	end

	self.Initialized = true
	
	-- setup initial gui format, then keep it live off the OS-resolved preference
	local function updatePreferredInput()
		local name = PREFERRED_INPUT_NAMES[UserInputService.PreferredInput]
		if name then
			self:deviceChange(name)
		end
	end

	updatePreferredInput()
	UserInputService:GetPropertyChangedSignal("PreferredInput"):Connect(updatePreferredInput)

	if self.InputType == "Touch" then
		task.defer(function()
			local viewportSize = CurrentCamera.ViewportSize
			while viewportSize.X + viewportSize.Y < 10 do
				viewportSize = CurrentCamera.ViewportSize
				task.wait()
			end
			
			local aspectRatio = viewportSize.X / viewportSize.Y
			local isTablet = true
			
			for _, range in ipairs(PHONE_ASPECT_RATIOS) do
				if aspectRatio >= range.Min and aspectRatio <= range.Max then
					isTablet = false
					break
				end
			end
			
			self.IsTablet = isTablet
		end)
	end
	
	-- handle event based inputs
	local function callMouseInputs(eventName, ...)
		for _, mappedInput in pairs(m.MappedInputs) do
			local methods = mappedInput.MouseInputs[eventName]
			if methods then
				for _, f in pairs(methods) do
					f(...)
				end
			end
		end
	end
	
	local function callTouchInputs(eventName, ...)
		for _, mappedInput in pairs(self.MappedInputs) do
			local methods = mappedInput.TouchInputs[eventName]
			if methods then
				for _, f in pairs(methods) do
					f(...)
				end
			end
		end
	end
	
	-- mouse support
	local function manageUIS(input, state, processed)
		local receivedType = input.UserInputType

		if receivedType == Enum.UserInputType.MouseMovement then
			callMouseInputs("Movement", input, state, processed)
		elseif receivedType == Enum.UserInputType.MouseWheel then
			callMouseInputs("Wheel", input, state, processed)
		elseif receivedType == Enum.UserInputType.MouseButton1 then
			callMouseInputs("Button1", input, state, processed)
		elseif receivedType == Enum.UserInputType.MouseButton2 then
			callMouseInputs("Button2", input, state, processed)
		elseif receivedType == Enum.UserInputType.MouseButton3 then
			callMouseInputs("Button3", input, state, processed)
		elseif receivedType == Enum.UserInputType.Touch then
			callTouchInputs("Touch", input, state, processed)
		end
	end
	
	UserInputService.InputBegan:Connect(function(input, processed)
		manageUIS(input, Enum.UserInputState.Begin, processed)
	end)

	UserInputService.InputChanged:Connect(function(input, processed)
		manageUIS(input, Enum.UserInputState.Change, processed)
	end)

	UserInputService.InputEnded:Connect(function(input, processed)
		manageUIS(input, Enum.UserInputState.End, processed)
	end)
	
	-- touch devices support
	UserInputService.TouchEnded:Connect(function(...)
		callTouchInputs("TouchEnded", ...)
	end)

	UserInputService.TouchStarted:Connect(function(...)
		callTouchInputs("TouchStarted", ...)
	end)
	
	UserInputService.TouchLongPress:Connect(function(...)
		callTouchInputs("TouchLongPress", ...)
	end)
	
	UserInputService.TouchMoved:Connect(function(...)
		callTouchInputs("TouchMoved", ...)
	end)
	
	UserInputService.TouchPan:Connect(function(...)
		callTouchInputs("TouchPan", ...)
	end)
	
	UserInputService.TouchPinch:Connect(function(...)
		callTouchInputs("TouchPinch", ...)
	end)
	
	UserInputService.TouchRotate:Connect(function(...)
		callTouchInputs("TouchRotate", ...)
	end)
	
	UserInputService.TouchSwipe:Connect(function(...)
		callTouchInputs("TouchSwipe", ...)
	end)
	
	UserInputService.TouchTap:Connect(function(...)
		callTouchInputs("TouchTap", ...)
	end)
	
	UserInputService.TouchTapInWorld:Connect(function(...)
		callTouchInputs("TouchTapInWorld", ...)
	end)
end

return m
