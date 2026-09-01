--[[
Exclusive:
	Used to exclusively replicate instances to single players.
]]

local NAME = "Replicated"

local HttpService = game:GetService("HttpService")

local m = {}

-- functions
function m:GetFolder(player: Player, generate: boolean?)
	assert(typeof(player) == "Instance" and player:IsA("Player"), "Exclusive.GetFolder | player must be an instance and a player")

	generate = generate == nil and true or generate

	local playerGui = player:FindFirstChild("PlayerGui")
	local result = playerGui and playerGui:FindFirstChild(NAME)
	if playerGui and not result and generate then
		result = Instance.new("Folder")
		result.Name = NAME
		result.Parent = playerGui
	end

	return result
end

-- NOTE: Once 'name' is instantiated the 'value' type is permanent until 'name' is removed via :Remove
function m:Set(player: Player, name: string, value: { [any] : any } | string | number | boolean | nil)
	assert(typeof(player) == "Instance" and player:IsA("Player"), "Exclusive.Set | player must be an instance and a player")
	assert(type(name) == "string", "Exclusive.Set | name must be a string")
	assert(type(value) == "table" or type(value) == "string" or type(value) == "number" or type(value) == "boolean" or value == nil, "Exclusive.Set | value must be a JSON-safe table or a string or a number or a boolean or nil")

	local folder = self:GetFolder(player)
	if not folder then
		return false
	end

	local object = folder:FindFirstChild(name)
	if value ~= nil then
		local valueType, expectedClassName = type(value), nil
		if valueType == "table" or valueType == "string" then
			expectedClassName = "StringValue"
		elseif valueType == "number" then
			expectedClassName = "NumberValue"
		elseif valueType == "boolean" then
			expectedClassName = "BoolValue"
		end

		if not object and expectedClassName then
			object = Instance.new(expectedClassName)

			if object then
				if valueType == "table" then
					object:SetAttribute("JSON", true)
				end

				object.Name = name
				object.Parent = folder
			end
		end

		if not object or object.ClassName ~= expectedClassName then
			return false
		end

		if valueType == "table" then
			value = HttpService:JSONEncode(value)
		end

		object.Value = value
	elseif object then
		object:Destroy()
		object = nil
	end

	return true
end

function m:Remove(player: Player, name: string)
	assert(typeof(player) == "Instance" and player:IsA("Player"), "Exclusive.Remove | player must be an instance and a player")
	assert(type(name) == "string", "Exclusive.Remove | name must be a string")

	return self:Set(player, name, nil)
end

return m
