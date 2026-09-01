local ServerScriptService = game:GetService("ServerScriptService")
local RunService = game:GetService("RunService")
local Players = game:GetService("Players")

local ProfileStore = require(ServerScriptService.Modules.ProfileStore)
local Default = require(script.Default)

export type Data = typeof(Default)

local Profiles, MessageHandlers = {}, {}
local Setups = {
	Pre = {},
	Post = {}
}

local m = {}

m.script = script

-- privates
function m:store()
	local store = ProfileStore.New("PlayerData", {})
	return RunService:IsStudio() and store.Mock or store
end

function m:defaultModule()
	return RunService:IsStudio() and script.Development or script.Default
end

function m:fix(t, d)
	-- backfills missing keys and resets any key whose stored typeof differs;
	-- migrations register pre-fix, updates post-fix
	for i, v in d do
		if t[i] == nil or typeof(t[i]) ~= typeof(v) then
			if typeof(v) == "table" then
				t[i] = {}
			else
				t[i] = v
			end
		end

		if typeof(v) == "table" then
			self:fix(t[i], d[i])
		end
	end

	return t
end

local function ownerOf(errorId)
	return string.match(errorId, "^([^.]+)%.")
end

local function runSetups(phase, player, data)
	for _, entry in Setups[phase] do
		local owner = ownerOf(entry.errorId)
		local subtree = owner and data[owner] or nil
		local success, msg = pcall(entry.fn, player, subtree)
		if not success then
			warn(entry.errorId .. " | " .. player.Name .. " | " .. tostring(msg))
		end
	end
end

local function dispatchMessage(player, message, processed)
	-- processed() before any yield; a saved message never redelivers
	if typeof(message) ~= "table" or MessageHandlers[message.Kind] == nil then
		warn("PlayerData.message | " .. player.Name .. " | no handler for kind '" .. tostring(typeof(message) == "table" and message.Kind) .. "'")
		return
	end

	processed()

	local entry = MessageHandlers[message.Kind]
	local success, msg = pcall(entry.fn, player, message.Data)
	if not success then
		warn(entry.name .. " | " .. player.Name .. " | " .. tostring(msg))
	end
end

-- functions
function m:AddSetup(phase, fn, errorId)
	assert(phase == "Pre" or phase == "Post", "PlayerData.AddSetup | phase must be \"Pre\" or \"Post\"")
	assert(typeof(fn) == "function", "PlayerData.AddSetup | fn must be a function")
	assert(typeof(errorId) == "string" and ownerOf(errorId) ~= nil, "PlayerData.AddSetup | errorId must be \"Service.method\"")

	table.insert(Setups[phase], { fn = fn, errorId = errorId })
end

function m:OnMessage(kind, fn, name)
	assert(typeof(kind) == "string" and kind ~= "", "PlayerData.OnMessage | kind must be a string")
	assert(typeof(fn) == "function", "PlayerData.OnMessage | fn must be a function")
	assert(typeof(name) == "string" and name ~= "", "PlayerData.OnMessage | name must be \"Service.handler\"")
	assert(MessageHandlers[kind] == nil, "PlayerData.OnMessage | duplicate handler for kind '" .. kind .. "'")

	MessageHandlers[kind] = { fn = fn, name = name }
end

function m:Send(userId, kind, data)
	-- offline delivery rides ProfileStore:MessageAsync; the profile's
	-- MessageHandler receives it on any server holding the session
	assert(typeof(kind) == "string" and kind ~= "", "PlayerData.Send | kind must be a string")
	assert(typeof(data) == "table", "PlayerData.Send | data must be a table")

	local success, msg = pcall(function()
		return self:store():MessageAsync(tostring(userId), {
			Kind = kind,
			Data = data,
		})
	end)

	if not success then
		warn("PlayerData.Send | " .. tostring(userId) .. " | " .. tostring(msg))
	elseif msg ~= true then
		-- MessageAsync reports failure by returning false, not by throwing
		warn("PlayerData.Send | " .. tostring(userId) .. " | MessageAsync returned false")
	end

	return success and msg == true
end

function m:Valid(player)
	return Profiles[player] ~= nil
end

function m:Get(player, owner)
	-- the second arg is the owning service and script.Name is the idiom — a
	-- service cannot name another's key without writing the literal out. The
	-- call returns only that top-level subtree; the whole-table view stays
	-- internal to PlayerData/
	assert(typeof(owner) == "string" and owner ~= "", "PlayerData.Get | owner must be script.Name")

	local profile = Profiles[player]
	if profile == nil then
		return nil
	end

	local subtree = profile.Data[owner]
	assert(subtree ~= nil, "PlayerData.Get | " .. owner .. " is not a top-level template key")
	return subtree
end

function m:Profile(player)
	-- internal to PlayerData/ and Payments' receipt hold; session profiles
	-- and view profiles never share a return path
	return Profiles[player]
end

function m:View(userId)
	local profile = self:store():GetAsync(tostring(userId))
	return profile and profile.Data or nil
end

m.PlayerAdded = function(player)
	local profile = m:store():StartSessionAsync(tostring(player.UserId), {
		Cancel = function()
			return not player:IsDescendantOf(Players)
		end,
	})

	if profile == nil then
		player:Kick("PlayerData | profile failed to load, rejoin")
		return
	end

	profile:AddUserId(player.UserId)

	profile.OnSessionEnd:Connect(function()
		Profiles[player] = nil
		player:Kick("PlayerData | session ended elsewhere, rejoin")
	end)

	if not player:IsDescendantOf(Players) then
		profile:EndSession()
		return
	end

	local defaultModule = m:defaultModule()
	local default = require(defaultModule)

	if defaultModule.Name == "Development" then
		profile.Data = m:fix({}, default)
	end

	runSetups("Pre", player, profile.Data)
	m:fix(profile.Data, default)
	runSetups("Post", player, profile.Data)

	profile:MessageHandler(function(message, processed)
		dispatchMessage(player, message, processed)
	end)

	Profiles[player] = profile
end

function m:Start()
	for _, player in Players:GetPlayers() do
		task.spawn(self.PlayerAdded, player)
	end

	Players.PlayerAdded:Connect(self.PlayerAdded)
	Players.PlayerRemoving:Connect(function(player)
		local profile = Profiles[player]
		if profile then
			profile:EndSession()
		end
	end)
end

-- events

return m
