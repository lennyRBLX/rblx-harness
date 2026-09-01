--[[
ViewportScale:
	Attaches a viewport-height-driven UIScale so offset-based / fixed-size UI keeps
	the same relative size on every device (phone, PC, 4K). Mirrors the Money /
	Experience HUD scaling: Scale = clamp(Camera.ViewportSize.Y / REFERENCE_HEIGHT, min, max).

	:attach(guiObject, min?, max?)        -> UIScale parented to guiObject (scales it + descendants).
	:scaleButton(frame, size, x, y, min?, max?) -> keeps frame square + left-anchored, scaling
	                                              both its size and its offset position by the factor.
]]

local REFERENCE_HEIGHT = 768

local m = {}

-- privates
local function bind(update)
	update()

	local camera = workspace.CurrentCamera
	local conn = camera and camera:GetPropertyChangedSignal("ViewportSize"):Connect(update)

	workspace:GetPropertyChangedSignal("CurrentCamera"):Connect(function()
		if conn then
			conn:Disconnect()
		end

		camera = workspace.CurrentCamera
		conn = camera and camera:GetPropertyChangedSignal("ViewportSize"):Connect(update)
		update()
	end)
end

local function factor(min, max)
	local camera = workspace.CurrentCamera
	local height = camera and camera.ViewportSize.Y or REFERENCE_HEIGHT

	return math.clamp(height / REFERENCE_HEIGHT, min, max)
end

-- functions
function m.attach(target, min, max)
	min = min or 0.7
	max = max or 1.6

	local scale = Instance.new("UIScale")
	scale.Name = "ViewportScale"

	bind(function()
		scale.Scale = factor(min, max)
	end)

	scale.Parent = target

	return scale
end

function m.scaleButton(frame, size, x, y, min, max)
	min = min or 0.7
	max = max or 1.6

	bind(function()
		local s = factor(min, max)
		frame.Size = UDim2.fromOffset(size * s, size * s)
		frame.Position = UDim2.new(0, x * s, 0.5, y * s)
	end)
end

return m
