local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Events = ReplicatedStorage:WaitForChild("Events")

local function serverCreate(f, asRemoteFunction)
	local event = Instance.new(asRemoteFunction and "RemoteFunction" or "RemoteEvent")
	-- Name & Parent get created in Server

	if f and not asRemoteFunction then
		event.OnServerEvent:Connect(f)
	elseif f then
		event.OnServerInvoke = f
	end

	return event
end

local function clientGet(service, name)
	local folder = Events:WaitForChild(service, 3)
	if not folder then
		warn("Event | FAILED TO FIND SERVICE FOLDER '" .. service, "' IN ReplicatedStorage.Events")
		return nil
	end
	
	local event = folder:WaitForChild(name, 0.01)
	if not event then
		warn("Event | FAILED TO FIND SERVICE EVENT '" .. name .. "' in " .. folder:GetFullName())
	end
	
	return event
end

return RunService:IsServer() and serverCreate or clientGet