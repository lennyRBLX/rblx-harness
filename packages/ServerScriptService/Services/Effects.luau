--[[
Effects:
	Manages communicating effects to be displayed to players. Fires the
	Manage event to the client-side Effects controller (prescribed template —
	vendored from the developer's standing stack by explicit ruling
	2026-07-06). Effects anchor to an entity (Player or Model) and are
	transient one-shots riding the remote by design (KNOWLEDGE_BASIS
	§3.4/§4); all rendering lives in the client controller's child handler
	modules — the server sends model, name, and method, never instances.

	The API is the standing stack's verbatim: Play is the one-shot,
	Activate/Deactivate bracket a sustained effect, and Call narrows the
	audience to an Include or Exclude filter. Every one asserts its arguments
	and returns false — never throws — when the entity has no model or no
	handler answers to the name. The wire order is (model, name, method, ...)
	and the controller dispatches on the method, so a handler added to the
	controller is reachable the moment it exists; the server learns nothing
	about it beyond the name.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterPlayer = game:GetService("StarterPlayer")
local Players = game:GetService("Players")

local Event = require(ReplicatedStorage.Packages.Event)

local m = {
	Events = {}
}

-- privates
local function exists(name: string): boolean
	-- the shared controller holds the effects every place gets; a place's own
	-- effects sit under PlaceChildren until the client grafts them on at
	-- start, so both roots have to answer before a name is called unknown
	local scripts = StarterPlayer.StarterPlayerScripts

	local controllers = scripts:FindFirstChild("Controllers")
	local shared = controllers and controllers:FindFirstChild("Effects")
	if shared and shared:FindFirstChild(name) then
		return true
	end

	local placeChildren = scripts:FindFirstChild("PlaceChildren")
	local place = placeChildren and placeChildren:FindFirstChild("Effects")
	if place and place:FindFirstChild(name) then
		return true
	end

	return false
end

local function resolve(entity: Player | Model): Model?
	if entity:IsA("Player") then
		return entity.Character
	elseif entity:IsA("Model") then
		return entity
	end

	return nil
end

local function broadcast(self, method: string, entity: Player | Model, name: string, ...)
	assert(
		typeof(entity) == "Instance" and (entity:IsA("Player") or entity:IsA("Model")),
		"Effects." .. method .. " | entity must be an Instance and a Player or a Model"
	)
	assert(typeof(name) == "string", "Effects." .. method .. " | name must be a string")

	if not exists(name) then
		return false
	end

	local model = resolve(entity)
	if not model then
		return false
	end

	self.Events["Manage"]:FireAllClients(model, name, method, ...)
	return true
end

-- functions
function m:Play(entity: Player | Model, name: string, ...)
	return broadcast(self, "Play", entity, name, ...)
end

function m:Activate(entity: Player | Model, name: string, ...)
	return broadcast(self, "Activate", entity, name, ...)
end

function m:Deactivate(entity: Player | Model, name: string, ...)
	return broadcast(self, "Deactivate", entity, name, ...)
end

function m:Call(filter: { Type: string, [number]: Player }, fromEntity: Player | Model, name: string, method: string, ...)
	assert(typeof(filter) == "table" and typeof(filter.Type) == "string", "Effects.Call | filter must be an table and include Type")
	assert(
		typeof(fromEntity) == "Instance" and (fromEntity:IsA("Player") or fromEntity:IsA("Model")),
		"Effects.Call | fromEntity must be an Instance and a Player or a Model"
	)
	assert(typeof(name) == "string", "Effects.Call | name must be a string")
	assert(typeof(method) == "string", "Effects.Call | method must be a string")

	local fromModel = resolve(fromEntity)
	if not fromModel then
		return false
	end

	local manage = self.Events["Manage"]

	if filter.Type == "Include" then
		for _, player in filter do
			if typeof(player) ~= "Instance" then
				continue
			end

			manage:FireClient(player, fromModel, name, method, ...)
		end
	elseif filter.Type == "Exclude" then
		for _, player in Players:GetPlayers() do
			if table.find(filter, player) then
				continue
			end

			manage:FireClient(player, fromModel, name, method, ...)
		end
	end

	return true
end

function m:Start()

end

-- events
m.Events["Manage"] = Event()

return m
