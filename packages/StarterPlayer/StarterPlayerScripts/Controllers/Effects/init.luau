--[[
Effects:
	Controls visual effects for the player. Manages child effect modules and
	responds to server-driven effect commands via the Effects service event
	(prescribed template — vendored from the developer's standing stack by
	explicit ruling 2026-07-06). Each direct child module is one effect
	handler exposing any of Play/Activate/Deactivate — Play for the one-shot,
	Activate/Deactivate to bracket a sustained effect — and each receives the
	anchoring model as its first argument. All rendering lives here.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Trove = require(ReplicatedStorage.Packages.Trove)
local Event = require(ReplicatedStorage.Packages.Event)

local m = {
	__cache = {},
	__hidden = {},
}

-- privates
function m:getEffect(name: string)
	local effect = self.__cache[name]
	if effect then
		return effect
	end

	local child = script:FindFirstChild(name)
	if not child then
		return nil
	end

	effect = require(child)
	self.__cache[name] = effect

	if effect.Start then
		effect:Start()
	end

	return effect
end

-- functions
function m:HideCharacter(model: Model)
	if self.__hidden[model] then
		return
	end

	local _t = Trove.new()
	self.__hidden[model] = _t
	_t:AttachToInstance(model)
	_t:Add(function()
		self.__hidden[model] = nil
	end)

	local function hide(obj)
		if obj:IsA("BasePart") and obj.Name ~= "HumanoidRootPart" then
			obj.Transparency = 1
			_t:Connect(obj:GetPropertyChangedSignal("Transparency"), function()
				if obj.Transparency ~= 1 then
					obj.Transparency = 1
				end
			end)
		elseif obj:IsA("Decal") then
			obj.Transparency = 1
			_t:Connect(obj:GetPropertyChangedSignal("Transparency"), function()
				if obj.Transparency ~= 1 then
					obj.Transparency = 1
				end
			end)
		end
	end

	for _, obj in model:GetDescendants() do
		hide(obj)
	end

	_t:Connect(model.DescendantAdded, hide)
end

function m:ShowCharacter(model: Model)
	local _t = self.__hidden[model]
	if not _t then
		return
	end

	_t:Destroy()

	for _, obj in model:GetDescendants() do
		if obj:IsA("BasePart") and obj.Name ~= "HumanoidRootPart" then
			obj.Transparency = 0
		elseif obj:IsA("Decal") then
			obj.Transparency = 0
		end
	end
end

function m:Play(model: Model, name: string, ...)
	local effect = self:getEffect(name)
	if not effect or not effect.Play then
		return false
	end

	effect:Play(model, ...)
	return true
end

function m:Activate(model: Model, name: string, ...)
	local effect = self:getEffect(name)
	if not effect or not effect.Activate then
		return false
	end

	effect:Activate(model, ...)
	return true
end

function m:Deactivate(model: Model, name: string, ...)
	local effect = self:getEffect(name)
	if not effect or not effect.Deactivate then
		return false
	end

	effect:Deactivate(model, ...)
	return true
end

function m:Resize(fx: Instance | { Instance }, multiplier: number)
	local effects = {}

	if typeof(fx) == "Instance" then
		for _, obj in fx:GetDescendants() do
			if obj:IsA("ParticleEmitter") then
				table.insert(effects, obj)
			end
		end

		if (fx :: Instance):IsA("ParticleEmitter") then
			table.insert(effects, fx)
		end
	elseif typeof(fx) == "table" then
		for _, effect in fx do
			for _, obj in effect:GetDescendants() do
				if obj:IsA("ParticleEmitter") and not table.find(effects, obj) then
					table.insert(effects, obj)
				end
			end

			if effect:IsA("ParticleEmitter") and not table.find(effects, effect) then
				table.insert(effects, effect)
			end
		end
	end

	for _, emitter in effects do
		local keys = {}
		for _, point in emitter.Size.Keypoints do
			table.insert(keys, NumberSequenceKeypoint.new(point.Time, point.Value * multiplier, point.Envelope))
		end

		emitter.Size = NumberSequence.new(keys)
	end
end

function m:Start()
	-- preload all child effects
	for _, child in script:GetChildren() do
		task.spawn(function()
			if not self:getEffect(child.Name) then
				warn("Effects | Failed to init '" .. child.Name .. "'")
			end
		end)
	end

	-- listen to server
	Event("Effects", "Manage").OnClientEvent:Connect(function(model: Model, name: string, method: string, ...)
		if self[method] then
			self[method](self, model, name, ...)
		end
	end)
end

return m
