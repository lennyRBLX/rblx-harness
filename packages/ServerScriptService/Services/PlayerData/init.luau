const CLEANUP_PLAYER = "PlayerData.Player"
const DEFAULT_STATE = {}

const ServerScriptService = game:GetService("ServerScriptService")
const ReplicatedStorage = game:GetService("ReplicatedStorage")
const RunService = game:GetService("RunService")
const Players = game:GetService("Players")
const IsStudio = RunService:IsStudio()

const EntityCleanup = require(ReplicatedStorage.Packages.EntityCleanup)
const ProfileStore = require(ServerScriptService.Modules.ProfileStore)
const TableUtil = require(ReplicatedStorage.Packages.TableUtil)
const Signal = require(ReplicatedStorage.Packages.Signal)
const Development = require(script.Development)
const Default = require(script.Default)

const PlayerDataTypes = require(ReplicatedStorage.Types.PlayerData)

const StoreOwner = ProfileStore.New("PlayerData", {})
const Store = if IsStudio then StoreOwner.Mock else StoreOwner
const Defaults = if IsStudio then Development else Default
const Profiles, PendingProfiles = {}, {}
const MessageHandlers = {}
const Setups = {
	Pre = {},
	Post = {}
}

-- Default's schema and each export type are generated together by data_write.
export type Data = typeof(Default)

const m = {
	Ready = Signal.new(),
	Released = Signal.new(),
	__players = {}
}

-- privates
const function fix(t, d)
	-- Backfill absent keys and reset values whose stored type has changed.
	for i, v in d do
		if t[i] == nil or typeof(t[i]) ~= typeof(v) then
			t[i] = if typeof(v) == "table" then {} else v
		end

		if typeof(v) == "table" then
			fix(t[i], d[i])
		end
	end

	return t
end

const function ownerOf(errorId)
	return string.match(errorId, "^([^.]+)%.")
end

const function runSetups(phase, player, data)
	for _, entry in table.clone(Setups[phase]) do
		if not entry.alive then
			continue
		end

		const owner = ownerOf(entry.errorId)
		const subtree = owner and data[owner] or nil
		const success, problem = pcall(entry.fn, player, subtree)
		if not success then
			warn(entry.errorId .. " | " .. player.Name .. " | " .. tostring(problem))
		end
	end
end

const function dispatchMessage(player, message, processed)
	if typeof(message) ~= "table" or not MessageHandlers[message.Kind] then
		warn("PlayerData.message | " .. player.Name .. " | no handler for kind '" .. tostring(typeof(message) == "table" and message.Kind) .. "'")
		return
	end

	processed()

	const entry = MessageHandlers[message.Kind]
	const success, problem = pcall(entry.fn, player, message.Data)
	if not success then
		warn(entry.name .. " | " .. player.Name .. " | " .. tostring(problem))
	end
end

const function cleanupPlayer(player, arguments)
	const state = m.__players[player]
	if not state or state ~= arguments[1] then
		return
	end

	m.__players[player] = nil
	state.Token = nil

	if state.Connection then
		state.Connection:Disconnect()
		state.Connection = nil
	end

	const profile = Profiles[player] or PendingProfiles[player]
	Profiles[player], PendingProfiles[player] = nil, nil

	if profile then
		profile:EndSession()
		m.Released:Fire(player)
	end
end

function m:playerAdded(player)
	if self.__players[player] or not player:IsDescendantOf(Players) then
		return
	end

	const state, token = TableUtil.Copy(DEFAULT_STATE, true), {}
	state.Token = token

	self.__players[player] = state
	EntityCleanup:Add(player, cleanupPlayer, { state }, CLEANUP_PLAYER)
	state.LoadTask = coroutine.create(function()
		const success, problem = pcall(function()
			const function current()
				return self.__players[player] == state and state.Token == token and player:IsDescendantOf(Players)
			end

			const profile = Store:StartSessionAsync(tostring(player.UserId), {
				Cancel = function()
					return not current()
				end
			})

			if not profile then
				if current() then
					player:Kick("PlayerData | profile failed to load, rejoin")
				end

				return
			elseif not current() then
				profile:EndSession()
				return
			end

			PendingProfiles[player] = profile
			profile:AddUserId(player.UserId)

			const sessionConnection = profile.OnSessionEnd:Connect(function()
				if self.__players[player] ~= state or (Profiles[player] ~= profile and PendingProfiles[player] ~= profile) then
					return
				end

				const success, problem = pcall(EntityCleanup.Remove, EntityCleanup, player, CLEANUP_PLAYER)
				if not success then
					warn("PlayerData.cleanup | " .. player.Name .. " | " .. tostring(problem))
				end

				if player:IsDescendantOf(Players) then
					player:Kick("PlayerData | session ended elsewhere, rejoin")
				end
			end)

			state.Connection = sessionConnection

			const function releaseStale()
				sessionConnection:Disconnect()

				if state.Connection == sessionConnection then
					state.Connection = nil
				end

				if PendingProfiles[player] == profile then
					PendingProfiles[player] = nil
				end

				profile:EndSession()
			end

			if not current() then
				releaseStale()
				return
			end

			if IsStudio then
				profile.Data = fix({}, Defaults)
			end

			runSetups("Pre", player, profile.Data)
			if not current() then
				releaseStale()
				return
			end

			fix(profile.Data, Defaults)
			runSetups("Post", player, profile.Data)

			profile:MessageHandler(function(message, processed)
				if self.__players[player] == state and Profiles[player] == profile then
					dispatchMessage(player, message, processed)
				end
			end)

			if not current() or not profile:IsActive() then
				releaseStale()
				return
			end

			PendingProfiles[player], state.Token = nil, nil
			Profiles[player] = profile
			self.Ready:Fire(player)
		end)

		state.LoadTask = nil

		if not success then
			if self.__players[player] == state then
				const removed, removalProblem = pcall(EntityCleanup.Remove, EntityCleanup, player, CLEANUP_PLAYER)
				if not removed then
					warn("PlayerData.cleanup | " .. player.Name .. " | " .. tostring(removalProblem))
				end
			end

			warn("PlayerData | load | " .. tostring(problem))
		end
	end)

	task.spawn(state.LoadTask)
end

-- functions
function m:GetState(player: Player): PlayerDataTypes.RuntimeState?
	return self.__players[player]
end

function m:AddSetup(phase, fn, errorId)
	assert(phase == "Pre" or phase == "Post", "PlayerData.AddSetup | phase must be \"Pre\" or \"Post\"")
	assert(typeof(fn) == "function", "PlayerData.AddSetup | fn must be a function")
	assert(typeof(errorId) == "string" and ownerOf(errorId), "PlayerData.AddSetup | errorId must be \"Service.method\"")

	const entry = { fn = fn, errorId = errorId, alive = true }
	table.insert(Setups[phase], entry)

	return function()
		entry.alive = false

		const index = table.find(Setups[phase], entry)
		if index then
			table.remove(Setups[phase], index)
		end
	end
end

function m:OnMessage(kind, fn, name)
	assert(typeof(kind) == "string" and kind ~= "", "PlayerData.OnMessage | kind must be a string")
	assert(typeof(fn) == "function", "PlayerData.OnMessage | fn must be a function")
	assert(typeof(name) == "string" and name ~= "", "PlayerData.OnMessage | name must be \"Service.handler\"")
	assert(not MessageHandlers[kind], "PlayerData.OnMessage | duplicate handler for kind '" .. kind .. "'")

	const entry = { fn = fn, name = name }
	MessageHandlers[kind] = entry

	return function()
		if MessageHandlers[kind] == entry then
			MessageHandlers[kind] = nil
		end
	end
end

function m:Send(userId, kind, data)
	assert(typeof(kind) == "string" and kind ~= "", "PlayerData.Send | kind must be a string")
	assert(typeof(data) == "table", "PlayerData.Send | data must be a table")

	const success, problem = pcall(Store.MessageAsync, Store, tostring(userId), { Kind = kind, Data = data })
	if not success then
		warn("PlayerData.Send | " .. tostring(userId) .. " | " .. tostring(problem))
	end

	return success
end

function m:Valid(player)
	const profile = Profiles[player]
	return profile and profile:IsActive() or false
end

function m:Get(player, owner)
	assert(typeof(owner) == "string" and owner ~= "", "PlayerData.Get | owner must be script.Name")

	const profile = Profiles[player]
	if not profile or not profile:IsActive() then
		return nil
	end

	const serviceData = profile.Data[owner]
	assert(serviceData, "PlayerData.Get | " .. owner .. " is not a top-level service key")
	return serviceData
end

function m:Profile(player)
	return Profiles[player]
end

function m:View(userId)
	const success, profile = pcall(Store.GetAsync, Store, tostring(userId))
	if not success then
		warn("PlayerData.View | " .. tostring(userId) .. " | " .. tostring(profile))
		return nil
	end

	return profile and profile.Data or nil
end

function m:Start()
	for _, player in Players:GetPlayers() do
		task.spawn(self.playerAdded, self, player)
	end

	Players.PlayerAdded:Connect(function(player)
		self:playerAdded(player)
	end)
end

return m
