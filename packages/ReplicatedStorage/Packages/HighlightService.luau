--!strict
-- HighlightService – mounts overlay in a new ScreenGui
-- Put this ModuleScript in ReplicatedStorage and require from a LocalScript.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local GuiService = game:GetService("GuiService")
local TweenService = game:GetService("TweenService")
local module = {}

export type Options = {
	generateDim: boolean?, -- default true
	showClicker: boolean?, -- default false
	padding: number?, -- px, default 8
	overlayTransparency: number?, -- 0..1, default 0.35
	overlayColor: Color3?, -- default black
	outlineColor: Color3?, -- default white
	outlineThickness: number?, -- px, default 2
	outlineTransparency: number?, -- 0..1, default 0
	clickerOffset: Vector2?, -- px, default (0,0)
	blockOutsideInput: boolean?, -- default true
	displayOrder: number?, -- used for the new ScreenGui
	ignoreGuiInset: boolean?, -- default true for the overlay ScreenGui
}

local ACTIVE_NAME = "TutorialSpotlight"

-- Create a new ScreenGui in PlayerGui for the overlay
local function createOverlayRoot(displayOrder: number, ignoreGuiInset: boolean?)
	local player = Players.LocalPlayer
	local playerGui = player:WaitForChild("PlayerGui")
	-- Clear any previous overlay
	for _, g in ipairs(playerGui:GetChildren()) do
		if g:IsA("ScreenGui") and g.Name == ACTIVE_NAME then
			g:Destroy()
		end
	end
	local sg = Instance.new("ScreenGui")
	sg.Name = ACTIVE_NAME
	sg.ResetOnSpawn = false
	sg.IgnoreGuiInset = ignoreGuiInset ~= false -- Default to true if not specified
	sg.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	sg.DisplayOrder = displayOrder
	sg.Parent = playerGui
	return sg
end

local function makeMask(name: string, color: Color3, trans: number, z: number, swallow: boolean)
	local f = Instance.new(swallow and "TextButton" or "Frame")
	f.Name = name
	f.BorderSizePixel = 0
	if f:IsA("TextButton") then f.AutoButtonColor = false end
	f.Active = swallow
	if f:IsA("TextButton") then f.Text = "" end
	f.BackgroundColor3 = color
	f.BackgroundTransparency = 1
	
	--for i,v in pairs({top,left,right,bot})do
		TweenService:Create(f,TweenInfo.new(0.4,Enum.EasingStyle.Sine),{BackgroundTransparency = trans}):Play()
	--end
	
	f.ZIndex = z
	return f
end

local function makeOutline(z: number, color: Color3, thickness: number, transparency: number)
	local frame = Instance.new("Frame")
	frame.Name = "Outline"
	frame.BackgroundTransparency = 1
	frame.BorderSizePixel = 0
	frame.ZIndex = z
	local stroke = Instance.new("UIStroke")
	stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	stroke.Thickness = thickness
	stroke.Color = color
	stroke.Transparency = transparency
	stroke.Parent = frame
	return frame
end

function module.Clicker(z: number, tweenedSize: UDim2?)
	local holder = Instance.new("ImageLabel")
	holder.Name = "Clicker"
	holder.BackgroundTransparency = 1
	holder.Size = UDim2.fromOffset(78, 78)
	holder.AnchorPoint = Vector2.new(0.5, 0.5)
	holder.Image = "http://www.roblox.com/asset/?id=100640210821551"
	holder.ZIndex = z
	local ring = Instance.new("Frame")
	ring.BackgroundTransparency = 1
	ring.Size = UDim2.fromScale(1, 1)
	ring.Parent = holder
	ring.ZIndex = z
	
	holder.ImageTransparency = 1
	

	local TS = game:GetService("TweenService")
	local TI = TweenInfo.new(0.8, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true)
	TS:Create(holder, TI, { Size = tweenedSize or UDim2.fromOffset(66, 66)}):Play()
	TS:Create(holder, TweenInfo.new(0.8,Enum.EasingStyle.Sine), {ImageTransparency = 0}):Play()

	return holder
end

local function paddedRect(target: GuiObject, padding: number)
	local p = target.AbsolutePosition
	local s = target.AbsoluteSize
	local x = math.floor(p.X - padding)
	local y = math.floor(p.Y - padding)
	local w = math.floor(s.X + padding * 2)
	local h = math.floor(s.Y + padding * 2)
	return x, y, w, h
end

function module.Spotlight(target: GuiObject, options: Options?)
	assert(target and target:IsA("GuiObject"), "Spotlight target must be a GuiObject")
	options = options or {}
	local generateDim = options.generateDim ~= false
	local showClicker = options.showClicker == true
	local padding = options.padding or 8
	local overlayTransparency = math.clamp(options.overlayTransparency or 0.35, 0, 1)
	local overlayColor = options.overlayColor or Color3.new(0, 0, 0)
	local outlineColor = options.outlineColor or Color3.new(1, 1, 1)
	local outlineThickness = options.outlineThickness or 2
	local outlineTransparency = math.clamp(options.outlineTransparency or 0, 0, 1)
	local blockOutside = options.blockOutsideInput ~= false
	local displayOrder = options.displayOrder or 50
	local ignoreGuiInset = options.ignoreGuiInset
	local onlyInset = options.onlyInset
	local noOutline = options.noOutline

	-- Mount overlay in a new ScreenGui
	local root = createOverlayRoot(displayOrder, ignoreGuiInset)

	-- Z layers within the same container
	local OVERLAY_Z = 10
	local FOREGROUND_Z = 11

	-- Create masks
	local top = makeMask("Top", overlayColor, overlayTransparency, OVERLAY_Z, generateDim and blockOutside or false); top.Parent = root
	local left = makeMask("Left", overlayColor, overlayTransparency, OVERLAY_Z, generateDim and blockOutside or false); left.Parent = root
	
	local bot, right = nil, nil
	if not onlyInset then
		bot = makeMask("Bottom", overlayColor, overlayTransparency, OVERLAY_Z, generateDim and blockOutside or false); bot.Parent = root
		right = makeMask("Right", overlayColor, overlayTransparency, OVERLAY_Z, generateDim and blockOutside or false); right.Parent = root
	end
	
	-- Outline + clicker
	local outline = nil
	if not noOutline then
		outline = makeOutline(FOREGROUND_Z, outlineColor, outlineThickness, outlineTransparency); outline.Parent = root
	end
	
	local clicker: GuiObject? = nil
	if showClicker then
		clicker = module.Clicker(FOREGROUND_Z)
		clicker.Parent = root
	end

	local function layout()
		if not target.Parent or not root.Parent then return end
		local screenW = root.AbsoluteSize.X
		local screenH = root.AbsoluteSize.Y
		
		local x, y, w, h = paddedRect(target, padding)
		-- Adjust y based on IgnoreGuiInset
		local yInset, xInset = GuiService:GetGuiInset()
		if ignoreGuiInset == true then
			y += yInset.Y
		end

		-- Clamp to container bounds
		x = math.max(0, math.min(x, screenW))
		y = math.max(0, math.min(y, screenH))
		w = math.max(0, math.min(w, screenW - x))
		h = math.max(0, math.min(h, screenH - y))

		-- Outline
		if outline then
			outline.Position = UDim2.fromOffset(x, y)
			outline.Size = UDim2.fromOffset(w, h)
			outline.Visible = true
		end

		-- Clicker
		if clicker then
			local clickerOffset = options.clickerOffset or Vector2.new(0, 0)
			local cx = x + w/2 + clickerOffset.X
			local cy = y + h/2 + clickerOffset.Y
			clicker.Position = UDim2.fromOffset(math.floor(cx + 0.5), math.floor(cy + 0.5))
			clicker.Visible = true
		end

		-- Masks
		if not onlyInset then
			bot.Visible = generateDim
			right.Visible = generateDim
		end
		
		top.Visible, left.Visible = generateDim, generateDim
		
		if generateDim then
			local dx, dy = onlyInset and xInset.X or x, onlyInset and yInset.Y or y
			
			top.Position = UDim2.fromOffset(0, 0)
			top.Size = UDim2.fromOffset(screenW, dy)
			
			if not onlyInset then
				local bottomY = y + h
				bot.Position = UDim2.fromOffset(0, bottomY)
				bot.Size = UDim2.fromOffset(screenW, math.max(0, screenH - bottomY))
				
				local rightX = x + w
				right.Position = UDim2.fromOffset(rightX, y)
				right.Size = UDim2.fromOffset(math.max(0, screenW - rightX), h)
			end
			
			left.Position = UDim2.fromOffset(0, dy)
			left.Size = UDim2.fromOffset(dx, h)
		end
	end

	-- Connections
	local conns: {RBXScriptConnection} = {
		target:GetPropertyChangedSignal("AbsolutePosition"):Connect(layout),
		target:GetPropertyChangedSignal("AbsoluteSize"):Connect(layout),
		root:GetPropertyChangedSignal("AbsoluteSize"):Connect(layout),
		root:GetPropertyChangedSignal("IgnoreGuiInset"):Connect(layout),
	}
	local stepConn = RunService.RenderStepped:Connect(layout)

	-- Initial layout with delay to ensure GuiService is ready
	task.wait(0.1)
	layout()

	-- Teardown
	return function()
		for _, c in ipairs(conns) do if c.Connected then c:Disconnect() end end
		if stepConn.Connected then stepConn:Disconnect() end
		if root then 
			
			for i,v in pairs({top,left,right,bot})do
				TweenService:Create(v,TweenInfo.new(0.4,Enum.EasingStyle.Sine),{BackgroundTransparency = 1}):Play()
			end
			
			TweenService:Create(clicker, TweenInfo.new(0.8,Enum.EasingStyle.Sine), {ImageTransparency = 1}):Play()

			
			--root:Destroy()
			game.Debris:AddItem(root,0.4)
		end -- Clean up the ScreenGui
	end
end

return module