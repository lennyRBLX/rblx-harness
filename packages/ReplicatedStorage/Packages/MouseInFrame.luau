local MAX_CACHE = 100

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local GuiService = game:GetService("GuiService")
local Players = game:GetService("Players")
local Player = Players.LocalPlayer

local Input = require(ReplicatedStorage.Packages.Input)

local PlayerGui = Player:WaitForChild("PlayerGui")
local Initialized, Cache = false, table.create(MAX_CACHE)

return function(frame, getCache: boolean?)
	if not Initialized then
		Initialized = true
		task.defer(function()
			while true do
				local mousePosition = UserInputService:GetMouseLocation() - GuiService:GetGuiInset()
				local guiObjects = PlayerGui:GetGuiObjectsAtPosition(mousePosition.X, mousePosition.Y)

				for i = 1, MAX_CACHE do
					Cache[i] = (guiObjects and guiObjects[i]) or nil
				end

				task.wait()
			end
		end)
	end
	
	local result = false
	if getCache then
		return Cache
	end
	
	for i = 1, MAX_CACHE do
		if Cache[i] == frame then
			result = true
			break
		end
	end

	return result
end