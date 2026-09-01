--[[
SoundPlayer:
	Module allows ease of access to play sounds
]]

local CLIENT_IDS = {
	Play = 0,
	PreloadAll = 1
}

local RunService = game:GetService("RunService")

local IS_SERVER = RunService:IsServer()
local IS_CLIENT = RunService:IsClient()

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ContentProvider = game:GetService("ContentProvider")
local SoundService = game:GetService("SoundService")
local Players = game:GetService("Players")

local Strings = require(script.Strings)
local EntityCleanup = require(ReplicatedStorage.Packages.EntityCleanup)

local Sounds = IS_SERVER and Instance.new("RemoteEvent") or ReplicatedStorage:WaitForChild("Sounds")
local Setup = IS_SERVER and Instance.new("RemoteFunction") or ReplicatedStorage:WaitForChild("Sounds.Setup")

local Player = Players.LocalPlayer

local m = {
	Cache = {},
	
	Loading = IS_SERVER and {} or nil,
	Loaded = IS_SERVER and {} or nil
}

-- privates
local function cleanupPlayer(player, arguments)
	m.Loading[player] = nil
	m.Loaded[player] = nil
end

function m:getParent(model)
	if model then
		local root = model:FindFirstChild("HumanoidRootPart")
		if root then
			return root
		elseif model:IsA("Model") and model.PrimaryPart then
			return model.PrimaryPart
		elseif model:IsA("BasePart") or model:IsA("Attachment") then
			return model
		end
	end

	return SoundService
end

-- functions
function m:Attach(matrix)
	assert(typeof(matrix) == "CFrame", "SoundPlayer.Attach | matrix must be a matrix")

	local result = Instance.new("Attachment")
	result.Parent = workspace.Terrain
	result.WorldCFrame = matrix
	
	return result
end

function m:IsValid(key)
	assert(type(key) == "string" or type(key) == "number", "SoundPlayer.IsValid | key must be a string or number")

	return not not Strings[key]
end

function m:WaitForName(model, key, maxWait)
	assert(type(key) == "string" or type(key) == "number", "SoundPlayer.WaitForName | key must be a string or number")
	assert(type(maxWait) == "number", "SoundPlayer.WaitForName | maxWait must be a number")

	local map = Strings[key]
	local id = (map and map.SoundId) or key

	local parent = self:getParent(model)
	local result = nil

	local childAdded, destroying = nil, nil
	local function cleanup()
		if childAdded then
			childAdded:Disconnect()
			childAdded = nil
		end

		if destroying then
			destroying:Disconnect()
			destroying = nil
		end
	end

	childAdded = parent.ChildAdded:Connect(function(obj)
		if obj:IsA("Sound") and obj.SoundId:find(tostring(id)) then
			childAdded:Disconnect()
			childAdded = nil

			result = obj
		end
	end)

	destroying = model.Destroying:Once(cleanup)

	for _, obj in pairs(parent:GetChildren()) do
		if obj:IsA("Sound") and obj.SoundId:find(tostring(id)) then
			result = obj
			break
		end
	end

	local t = tick()
	while not result or not destroying do
		if tick() - t > maxWait then
			break
		end

		task.wait()
	end

	cleanup()
	return result
end

function m:GetFromName(model, name)
	assert(type(name) == "string", "SoundPlayer.GetFromName | name must be a string")

	local parent = self:getParent(model)
	local sounds = {}

	for key, info in pairs(self.Cache) do
		for sound, _ in pairs(info.Running) do
			if sound.Parent == parent and sound.Name == name then
				sounds[#sounds + 1] = sound
			end
		end
	end

	return sounds
end

function m:Get(model, key)
	assert(type(key) == "string" or type(key) == "number", "SoundPlayer.Get | key must be a string or number")
	
	local map = Strings[key]
	local id = (map and map.SoundId) or key
	local info = self.Cache[id]
	if not info then
		return nil
	end

	local parent = self:getParent(model)
	for sound, _ in pairs(info.Running) do
		if sound.Parent == parent then
			return sound
		end
	end
	
	return nil
end

function m:Play(model, key, properties)
	assert(type(key) == "string" or type(key) == "number", "SoundPlayer.Play | key must be a string or number")
	assert(type(properties) == "table" or type(properties) == "string" or properties == nil, "SoundPlayer.Play | properties must be a table or a string or nil")

	if properties == "WorldDefault" or properties == "UIDefault" then
		properties = { SoundGroup = properties == "WorldDefault" and "World" or "UI" }
	end
	
	local parent = self:getParent(model)
	if not key or key == 0 or (type(key) == "string" and not self:IsValid(key)) or not parent then
		return nil
	end
	
	local map = Strings[key]
	local id = (map and map.SoundId) or key
	if type(id) == "string" then
		return nil
	end

	local info = self.Cache[id]
	if not info then
		info = {
			Loaded = false,
			Running = {}
		}
		
		self.Cache[id] = info
	end
	
	local player = IS_SERVER and Players:GetPlayerFromCharacter(model)
	local result = nil

	local dontPlay = (properties and properties.DontPlay) or false
	local onServer = (properties and properties.OnServer) or false
	local exclusive = (properties and properties.Exclusive) or false
	if properties then
		properties.RollOffMaxDistance = properties.RollOffMaxDistance or 300
		properties.DontPlay = nil
		properties.OnServer = nil
		properties.Exclusive = nil
	end

	if IS_SERVER and dontPlay then
		if not player then
			Sounds:FireAllClients(false, CLIENT_IDS.Play, model, key, properties or {})
		elseif self.Loaded[player] then
			Sounds:FireClient(player, false, CLIENT_IDS.Play, model, key, properties or {})
		else
			local loading = self.Loading[player]
			if not loading then
				loading = {}
				self.Loading[player] = loading
			end

			loading[#loading + 1] = key
		end
	elseif not dontPlay then
		if IS_SERVER and not onServer then
			if not player or not exclusive then
				Sounds:FireAllClients(false, CLIENT_IDS.Play, model, key, properties or {})
			elseif player then
				Sounds:FireClient(player, false, CLIENT_IDS.Play, model, key, properties or {})
			end
		elseif tonumber(id) then
			result = Instance.new("Sound")
			result.Name = tostring(key)
			result.SoundId = "rbxassetid://" .. tostring(id)
			
			if map then
				self:Modify(result, map)
			end

			result.Parent = parent
			info.Running[result] = true

			while not result.IsLoaded do
				task.wait()
			end

			info.Loaded = true
			if properties then
				self:Modify(result, properties)
			end
			
			result:Play()

			local stopped, ended = nil, nil
			local function cleanup()
				if stopped then
					stopped:Disconnect()
					stopped = nil
				end

				if ended then
					ended:Disconnect()
					ended = nil
				end

				local object = result.Parent
				if not object or not object:IsA("Attachment") then
					object = result
				end

				info.Running[result] = nil
				task.delay(0.1, object.Destroy, object)
			end
			
			stopped = result.Stopped:Once(function()
				stopped = nil
				cleanup()
			end)

			ended = result.Ended:Once(function()
				ended = nil
				cleanup()
			end)
		end
	end
	
	return result
end

function m:Preload(model, key)
	assert(type(key) == "string" or type(key) == "number", "SoundPlayer.Preload | key must be a string or a number")

	self:Play(model, key, {
		DontPlay = true
	})

	return true
end

function m:PreloadAll(ids)
	if IS_CLIENT and ids then
		local character = Player.Character or Player.CharacterAdded:Wait()
		local strings = table.clone(Strings)
		
		for _, id in pairs(ids) do
			local key = id
			for k, properties in pairs(strings) do
				if properties.SoundId == id then
					key = k
					break
				end
			end

			strings[key] = nil
			self:Preload(character, key)
		end

		table.clear(strings)
		self:PreloadAll()
		return
	end

	local sounds, allIds = {}, {}
	for id, info in pairs(self.Cache) do
		if not info.Loaded then
			local sound = Instance.new("Sound")
			sound.SoundId = "rbxassetid://" .. id
			sound.Volume = 0
			sound.Parent = SoundService

			table.insert(sounds, sound)
		end

		table.insert(allIds, id)
	end

	if IS_SERVER then
		Sounds:FireAllClients(false, CLIENT_IDS.PreloadAll, allIds)
	end

	if #sounds > 0 then
		ContentProvider:PreloadAsync(sounds, function(assetId, status)
			if status ~= Enum.AssetFetchStatus.Success then
				return
			end
			
			local id = tonumber(assetId:match("%d+"))
			local info = self.Cache[id]
			info.Loaded = true
		end)
	end
end

function m:End(sound)
	assert(typeof(sound) == "Instance" and sound:IsA("Sound"), "SoundPlayer.End | sound must be an Sound") 
	
	sound:Stop()
end

function m:Modify(sound, properties)
	assert(typeof(sound) == "Instance" and sound:IsA("Sound"), "SoundPlayer.Modify | sound must be an Sound")
	assert(type(properties) == "table", "SoundPlayer.Modify | properties must be a table")

	-- custom
	if properties.SoundGroup then
		local group = (type(properties.SoundGroup) == "string" and SoundService:FindFirstChild(properties.SoundGroup)) or nil
		sound.SoundGroup = group
	end

	-- generic
	properties = table.clone(properties)
	properties.SoundGroup = nil
	properties.SoundId = nil

	for k, v in pairs(properties) do
		local s, m = pcall(function()
			return sound[k]
		end)

		if s and typeof(m) == typeof(v) then
			sound[k] = v
		end
	end

	-- cleanup
	table.clear(properties)
end

function m:Freeze(sound, position, isPercentage)
	assert(typeof(sound) == "Instance" and sound:IsA("Sound"), "SoundPlayer.Freeze | sound must be an Sound")
	
	if typeof(position) == "number" then
		if not sound.IsPlaying then
			sound:Play()
		end
	
		sound.TimePosition = isPercentage and (position / 100) * sound.TimeLength or position
	end
	
	sound:Pause()
end

if IS_SERVER then
	Sounds.Name = "Sounds"
	Sounds.Parent = ReplicatedStorage

	Setup.OnServerInvoke = function(player)
		local result = m.Loading[player]
		m.Loaded[player] = true
		m.Loading[player] = nil
		
		EntityCleanup:Add(player, cleanupPlayer, nil, "SoundPlayer.cleanupPlayer")
		return result
	end

	Setup.Name = "Sounds.Setup"
	Setup.Parent = ReplicatedStorage
elseif IS_CLIENT then
	Sounds.OnClientEvent:Connect(function(source, id, ...)
		if source then
			return
		end

		local args = { ... }
		if id == CLIENT_IDS.Play then
			local properties, key, model = table.remove(args), table.remove(args), table.remove(args)
			m:Play(model, key, properties)
		elseif id == CLIENT_IDS.PreloadAll then
			local keys = table.remove(args)
			m:PreloadAll(keys)
		end

		table.clear(args)
	end)

	task.spawn(function()
		local preloadList = Setup:InvokeServer() or {}
		for key, _ in pairs(Strings) do
			table.insert(preloadList, key)
		end

		for _, key in pairs(preloadList) do
			m:Preload(nil, key)
		end

		task.wait()
		m:PreloadAll()
	end)
end

return m
