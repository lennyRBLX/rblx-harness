local NAME = "Replicated"

local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")

local Player = Players.LocalPlayer

-- PlayerGui is created once per player and survives respawns; the Replicated folder under it does NOT.
-- With StarterGui.ResetPlayerGuiOnSpawn (default true) Roblox destroys that folder on every respawn and
-- the server recreates a fresh instance, so a folder reference cached here at module load would point at
-- the destroyed folder — every read after the first death then errors / returns nothing, silently killing
-- sprint, slows, freeze, settings and any other exclusive-replicated state. Re-resolve the live folder
-- against the persistent PlayerGui on each call instead.
local PlayerGui = Player:WaitForChild("PlayerGui")

return function(name: string, get: boolean?, find: boolean?)
	local Replicated
	if find then
		Replicated = PlayerGui:FindFirstChild(NAME)
	else
		Replicated = PlayerGui:WaitForChild(NAME)
	end

	if not Replicated then
		return nil
	end

	local info = (find and Replicated.FindFirstChild or Replicated.WaitForChild)(Replicated, name)
	local result = info

	if get and info then
		local success = false
		result = nil

		while not success do
			success, result = false, nil
			if info:GetAttribute("JSON") then
				success, result = pcall(HttpService.JSONDecode, HttpService, info.Value)
			else
				success, result = true, info.Value
			end

			if not success then
				task.wait()
			end
		end
	end

	return result
end
