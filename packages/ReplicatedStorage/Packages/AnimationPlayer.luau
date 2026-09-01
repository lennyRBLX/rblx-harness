--[[
AnimationPlayer:
	Module allows ease of access to play animations
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ContentProvider = game:GetService("ContentProvider")
local StarterPlayer = game:GetService("StarterPlayer")
local Players = game:GetService("Players")

local Animate = StarterPlayer.StarterCharacterScripts:FindFirstChild("Animate")
local Player = Players.LocalPlayer
local CombatAnimations = {}

local m = {
	Filter = {},
	Cache = {}
}

-- privates
local function isPast(current, timeOfKeyframe, reversed)
	return (not reversed and current >= timeOfKeyframe) or (reversed and current <= timeOfKeyframe) or false
end

-- functions
function m:WaitForName(rig, name, maxWait, onlyPlaying)
	assert(type(name) == "number", "AnimationPlayer.WaitForName | name must be a number")
	assert(type(maxWait) == "number", "AnimationPlayer.WaitForName | maxWait must be a number")

	rig = typeof(rig) == "Instance" and rig:IsA("Model") and rig or Player.Character

	local result, animator = nil, rig:FindFirstChild("Animator", true)
	if not animator then
		return result
	end

	local animationPlayed, destroying = nil, nil
	local function cleanup()
		if animationPlayed then
			animationPlayed:Disconnect()
			animationPlayed = nil
		end

		if destroying then
			destroying:Disconnect()
			destroying = nil
		end
	end

	animationPlayed = animator.AnimationPlayed:Connect(function(track)
		if track.Animation.AnimationId:find(tostring(name)) then
			animationPlayed:Disconnect()
			animationPlayed = nil

			result = track
		end
	end)

	destroying = rig.Destroying:Once(cleanup)

	for _, track in pairs(animator:GetPlayingAnimationTracks()) do
		if track.Animation.AnimationId:find(tostring(name)) and (not onlyPlaying or track.IsPlaying) then
			result = track
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

function m:AddToFilter(id)
	assert(type(id) == "string" or type(id) == "number", "AnimationPlayer.GetFromName | id must be a string or number")

	self.Filter[tostring(id)] = true
end

function m:GetFromName(rig, name)
	assert(type(name) == "string", "AnimationPlayer.GetFromName | name must be a string")

	rig = typeof(rig) == "Instance" and rig:IsA("Model") and rig or Player.Character

	local animator = rig:FindFirstChild("Animator", true) or rig:FindFirstChild("Humanoid")
	if not animator then
		return {}
	end

	local animations = {}
	for key, info in pairs(self.Cache) do
		for i, track in pairs(info.Tracks) do
			if i == animator and track.Name == name then
				animations[#animations + 1] = track
			end
		end
	end

	return animations
end

function m:Get(rig, key)
	assert(type(key) == "number", "AnimationPlayer.Get | key must be a number")
	
	rig = typeof(rig) == "Instance" and rig:IsA("Model") and rig or Player.Character

	local animator = rig:FindFirstChild("Animator", true) or rig:FindFirstChild("Humanoid")
	if not animator then
		return nil
	end
	
	local animation = self.Cache[key]
	if animation and animation.Tracks[animator] then
		return animation.Tracks[animator]
	end
	
	return nil
end

function m:Play(rig, key, properties)
	assert(type(key) == "number" or (typeof(key) == "Instance" and key:IsA("Animation")), "AnimationPlayer.Play | key must be a number or an Animation")
	assert(typeof(properties) == "table", "AnimationPlayer.Play | properties must be a table")
	
	rig = typeof(rig) == "Instance" and rig:IsA("Model") and rig or Player.Character

	if key == 0 or not rig then
		return nil
	end

	while not rig.Parent do
		task.wait()
	end
	
	local animator = rig:FindFirstChild("Animator", true) or rig:FindFirstChild("Humanoid")
	if not animator then
		return nil
	end
	
	local isInstance = typeof(key) == "Instance"
	local animId = isInstance and (key :: Animation).AnimationId or ("rbxassetid://" .. tostring(key))

	local animation = self.Cache[key]
	if not animation then
		local animationObj = isInstance and key :: Animation or Instance.new("Animation")
		if not isInstance then
			animationObj.AnimationId = animId
		end

		self.Cache[key] = {
			Loaded = false,
			Animation = animationObj,
			Tracks = {}
		}
		
		animation = self.Cache[key]
	end
	
	local result = animation.Tracks[animator]
	if not result then
		result = animator:LoadAnimation(animation.Animation)
		result.Priority = Enum.AnimationPriority.Action
		animation.Tracks[animator] = result

		local ancestryChanged = nil
		ancestryChanged = animator.AncestryChanged:Connect(function(_, parent)
			if parent == nil then
				ancestryChanged:Disconnect()
				ancestryChanged = nil

				animation.Tracks[animator] = nil
				animator = nil
			end
		end)
	end

	if properties.AsIs then
		return result
	end
	
	while result.Length == 0 do
		task.wait()
	end
	
	if properties.Looped then
		self:Modify(result, { Looped = properties.Looped })
	end

	if properties.Priority then
		self:Modify(result, { Priority = properties.Priority })
	end

	local beforePlay = properties.BeforePlay
	if beforePlay then
		self:Modify(result, properties)
		properties.BeforePlay = nil
	end

	if properties.DontPlay then
		if not result.IsPlaying then
			result:Play(0, 0.001, 1337)
			result:Stop(0)
		end
	else
		if properties.Prioritize then
			for _, track in pairs(animator:GetPlayingAnimationTracks()) do
				-- TBD: ADD FILTER SELECTION LISTS TO CHOOSE FROM WHEN PLAYING ANIMATIONS
				if (properties.Looped and track == result) then
					continue
				end

				local filtered, animationId = false, track.Animation.AnimationId
				for filterId, _ in pairs(self.Filter) do
					if animationId:find(filterId) then
						filtered = true
						break
					end
				end

				if filtered then
					continue
				end

				track:Stop(typeof(properties.FadeTime) == "number" and properties.FadeTime or 0)
			end
		end

		if not properties.Looped or not result.IsPlaying then
			properties.Speed = (tonumber(properties.Speed) or 1)

			result:Play(properties.FadeTime, 1, 1)

			if not beforePlay then
				self:Modify(result, properties)
			end

			result.Ended:Once(function()
				self:Modify(result, {
					Speed = 1,
					Priority = Enum.AnimationPriority.Action,
					TimePosition = 0
				})
			end)
		end
	end
	
	if not beforePlay then
		self:Modify(result, properties)
	end
	
	return result
end

function m:Destroy(animation)
	assert(typeof(animation) == "Instance" and animation:IsA("AnimationTrack"), "AnimationPlayer.Destroy | animation must be an AnimationTrack")

	for _, info in pairs(self.Cache) do
		local found = false
		for animator, track in pairs(info.Tracks) do
			if track == animation then
				found = true
				info.Tracks[animator] = nil
				break
			end
		end

		if found then
			break
		end
	end

	pcall(animation.Destroy, animation)
end

function m:Preload(rig, key, async)
	assert(type(key) == "number", "AnimationPlayer.Preload | key must be a number")

	rig = typeof(rig) == "Instance" and rig:IsA("Model") and rig or Player.Character
	
	while not rig.Parent do
		task.wait()
	end
	
	local animator = rig:FindFirstChild("Animator", true) or rig:FindFirstChild("Humanoid")
	if not animator then
		return false, nil
	end

	local animation = nil
	if async then
		animation = self:Play(rig, key, { DontPlay = true })
	else
		task.spawn(self.Play, self, rig, key, { DontPlay = true })
	end

	return true, animation
end

function m:PreloadAll()
	local animations = {}
	for key, info in pairs(self.Cache) do
		local animation = info.Animation
		if not animation or info.Loaded then
			continue
		end

		table.insert(animations, animation)
	end

	if #animations > 0 then
		task.spawn(ContentProvider.PreloadAsync, ContentProvider, animations, function(assetId, status)
			if status ~= Enum.AssetFetchStatus.Success then
				return
			end
			
			local key = tonumber(assetId:match("%d+"))
			local info = self.Cache[key]
			info.Loaded = true
		end)
	end
end

function m:WaitForKey(animation, key, reversed)
	if not animation.IsPlaying then
		return false, false
	end

	while animation.Length == 0 do
		task.wait()
	end

	local s, timeOfKeyframe = pcall(animation.GetTimeOfKeyframe, animation, key)
	if not s or isPast(animation.TimePosition, timeOfKeyframe, reversed) then
		return animation.TimePosition == timeOfKeyframe, nil
	end

	local stopped, stoppedConnection, keyReachedConnection = false, nil, nil
	stoppedConnection = animation.Stopped:Connect(function()
		if stoppedConnection then
			stoppedConnection:Disconnect()
			stoppedConnection = nil
		end

		if keyReachedConnection then
			keyReachedConnection:Disconnect()
			keyReachedConnection = nil
		end

		stopped = true
	end)

	local keyReached = nil
	keyReachedConnection = animation.KeyframeReached:Connect(function(name)
		if keyReached ~= key then
			keyReached = name
		end
	end)

	while keyReached ~= key and not isPast(animation.TimePosition, timeOfKeyframe, reversed) and not stopped do
		task.wait()
	end

	if stoppedConnection then
		stoppedConnection:Disconnect()
		stoppedConnection = nil
	end

	if keyReachedConnection then
		keyReachedConnection:Disconnect()
		keyReachedConnection = nil
	end

	return true, keyReached == key
end

function m:WaitForMarker(animation, marker, unsafe)
	if not animation.IsPlaying then
		return false, false
	end

	if unsafe then
		animation:GetMarkerReachedSignal(marker):Wait()
		return true, true
	end

	local stopped, stoppedConnection, markerReachedConnection = false, nil, nil
	stoppedConnection = animation.Stopped:Connect(function()
		if stoppedConnection then
			stoppedConnection:Disconnect()
			stoppedConnection = nil
		end

		if markerReachedConnection then
			markerReachedConnection:Disconnect()
			markerReachedConnection = nil
		end

		stopped = true
	end)

	local markerReached = false
	markerReachedConnection = animation:GetMarkerReachedSignal(marker):Connect(function()
		markerReached = true
	end)

	while not markerReached and not stopped do
		task.wait()
	end

	if stoppedConnection then
		stoppedConnection:Disconnect()
		stoppedConnection = nil
	end

	if markerReachedConnection then
		markerReachedConnection:Disconnect()
		markerReachedConnection = nil
	end

	return true, markerReached
end

function m:Stop(animation)
	assert(typeof(animation) == "Instance" and animation:IsA("AnimationTrack"), "AnimationPlayer.Stop | animation must be an AnimationTrack") 
	
	animation:Stop(0)
	animation.Parent = nil
end

function m:Modify(animation, properties)
	assert(typeof(animation) == "Instance" and animation:IsA("AnimationTrack"), "AnimationPlayer.Modify | animation must be an AnimationTrack")
	assert(typeof(properties) == "table", "AnimationPlayer.Modify | properties must be a table")
	
	-- custom
	if properties.Speed then
		animation:AdjustSpeed(properties.Speed)
	end
	
	if properties.Weight then
		animation:AdjustWeight(tonumber(properties.Weight.Value) or animation.WeightCurrent, tonumber(properties.Weight.Fade) or 0)
	end
	
	if properties.Length then
		animation:AdjustSpeed(animation.Length / properties.Length)
	end

	-- generic
	local propertiesClone = table.clone(properties)
	propertiesClone.Speed = nil
	propertiesClone.Weight = nil
	propertiesClone.Length = nil

	for k, v in pairs(propertiesClone) do
		local s, m = pcall(function()
			return animation[k]
		end)

		if s and typeof(m) == typeof(v) then
			animation[k] = v
		end
	end

	-- cleanup
	table.clear(propertiesClone)
end

function m:Freeze(animation, position, isPercentage)
	assert(typeof(animation) == "Instance" and animation:IsA("AnimationTrack"), "AnimationPlayer.Freeze | animation must be an AnimationTrack")
	
	self:Modify(animation, {
		Speed = 0
	})
	
	if type(position) == "number" then
		if not animation.IsPlaying then
			animation:Play()
		end
	
		animation.TimePosition = isPercentage and (position / 100) * animation.Length or position
	end
end

if ReplicatedStorage:FindFirstChild("Shared") and ReplicatedStorage.Shared:FindFirstChild("CombatInfo") then
	local abilities = ReplicatedStorage.Shared.CombatInfo:FindFirstChild("NenAbilities")
	local styles = ReplicatedStorage.Shared.CombatInfo:FindFirstChild("CombatStyles")
	
	for _, folder in pairs({ abilities, styles }) do
		for _, tag in pairs(folder:GetChildren()) do
			local module = tag:FindFirstChild("Animations")
			if not module then
				continue
			end

			local success, animations = pcall(require, module)
			if not success then
				continue
			end

			for _, info in pairs(animations) do
				if type(info) == "table" and tonumber(info.ID) then
					CombatAnimations[info.ID] = true
				end
			end
		end
	end
end

if Animate then
	for _, obj in pairs(Animate:GetDescendants()) do
		if obj:IsA("Animation") then
			m:AddToFilter(obj.AnimationId)
		end
	end
end

return m
