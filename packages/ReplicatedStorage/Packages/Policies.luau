local IS_CLIENT = game:GetService("RunService"):IsClient()

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local PolicyService = game:GetService("PolicyService")
local RunService = game:GetService("RunService")
local Players = game:GetService("Players")

local Player = Players.LocalPlayer

local EntityCleanup = require(ReplicatedStorage.Packages.EntityCleanup)
local Retry = require(ReplicatedStorage.Packages.Retry)

local m = {
	__fetching = {},
	__cache = {}
}

-- functions
function m:Get(player: Player | nil)
	player = (IS_CLIENT and Player) or player

	while self.__fetching[player] and player.Parent do
		task.wait()
	end

	if not player.Parent then
		return nil
	end

	local result = self.__cache[player]
	if result then
		return result
	end

	self.__fetching[player] = true

	local success = false
	success, result = Retry(15, 30, PolicyService.GetPolicyInfoForPlayerAsync, PolicyService, player)
	self.__fetching[player] = nil

	if not success or not player.Parent then
		return nil
	end

	self.__cache[player] = result
	return result
end

if not IS_CLIENT then
	Players.PlayerRemoving:Connect(function(player)
		m.__fetching[player] = nil
		m.__cache[player] = nil
	end)
end

return m