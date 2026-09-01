--[[
EntityCleanup:
	Manages storing singleton Trove's for entities &
	making cross-system cleanup easier.

NOTE: Automatically cleans up Player's on PlayerRemoving in LocalMain & ServerMain, & AI in WorldAI on Death.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Trove = require(ReplicatedStorage.Packages.Trove)

local m = {
	Troves = {}
}

-- private functions
local function cleanupEntity(entity)
	m.Troves[entity] = nil
end

-- functions
function m:GetInfo(entity: Player | Model)
	return self.Troves[entity]
end

function m:Setup(entity: Player | Model)
	local info = self:GetInfo(entity)
	if info then
		return info
	end

	info = {
		_t = Trove.new(),
		methods = {}
	}

	self.Troves[entity] = info
	self:Add(entity, cleanupEntity, nil, "EntityCleanup.cleanupEntity")
	
	return info
end

function m:Add(entity: Player | Model, cleanup: (entity: Player | Model, arguments: { [number] : any } | nil) -> boolean?, arguments: { [number] : any } | nil, name: string?)
	assert(typeof(arguments) == "table" or not arguments, "EntityCleanup.Add | arguments must be a table or nil")
	
	local info = self:GetInfo(entity)
	if not info then
		info = self:Setup(entity)
	end

	local method = nil
	if name and info.methods[name] then
		method = info.methods[name]
	end

	if not method then
		local entityName = entity.Name

		if arguments then
			method = function()
				local success, msg = pcall(cleanup, entity, arguments)
				table.clear(arguments)

				if not success or msg == false then
					local definer = ""
					if not success then
						definer ..= "Error in Cleanup: " .. (msg ~= false and msg or "")
					else
						definer ..= "Failed to Cleanup"
					end

					warn(name .. " | " .. entityName .. " | " .. definer)
				end
			end
		else
			method = function()
				local success, msg = pcall(cleanup, entity)
				if not success or msg == false then
					local definer = ""
					if not success then
						definer ..= "Error in Cleanup: " .. (msg ~= false and msg or "")
					else
						definer ..= "Failed to Cleanup"
					end

					warn(name .. " | " .. entityName .. " | " .. definer)
				end
			end
		end
	end

	if name and not info.methods[name] then
		info.methods[name] = method
	end

	info._t:Add(method)
end

function m:Remove(entity: Player | Model, name: string)
	local info = self:GetInfo(entity)
	if not info then
		return false
	end

	local f = info.methods[name]
	if not f then
		return false
	end

	info.methods[name] = nil
	return info._t:Remove(f)
end

function m:Cleanup(entity: Player | Model)
	local info = self:GetInfo(entity)
	if not info then
		return false
	end

	info._t:Clean()
	table.clear(info.methods)
	return true
end

return m
