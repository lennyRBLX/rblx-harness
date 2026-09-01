local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")

local MouseInFrame = require(ReplicatedStorage.Packages.MouseInFrame)
local Input = require(ReplicatedStorage.Packages.Input)

local Player = Players.LocalPlayer
local PlayerGui = Player:WaitForChild("PlayerGui")

return function()
	local result = false
	if Input.InputType ~= "Touch" then
		return result
	end
	
	local touchGui = PlayerGui:FindFirstChild("TouchGui")
	local touchControlFrame = touchGui and touchGui:FindFirstChild("TouchControlFrame") or nil
	if not touchControlFrame then
		return result
	end
	
	local cache = MouseInFrame(nil, true)
	for _, button in pairs(touchControlFrame:GetChildren()) do
		if table.find(cache, button) then
			result = true
			break
		end
	end

	return result
end