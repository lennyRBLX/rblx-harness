--!optimize 2
--!strict

-- 05/13/26
-- @t003z

-- TYPES
type ParticleObject = {
	Lifetime: number,
	Transform: CFrame,
	Velocity: Vector3,
	MeshPart: MeshPart?,
	Width: number,
	SplatterWidth: number?,
	Splashed: boolean
}
-- per-call overrides so a caller (e.g. the Mimic vomit) can spawn larger droplets + bigger floor
-- pools without mutating the shared global Settings (which would compound across concurrent callers)
export type BloodOptions = {
	ParticleWidth: number?, -- droplet (flying) width; nil → random from Settings.ParticleWidth
	SplatterWidth: number?, -- floor-pool width for the splatter this droplet makes; nil → Settings
}
export type PublicModule = {
	new: (Position: Vector3, Direction: Vector3, Force: number, Options: BloodOptions?) -> (),
	Clean: () -> (),
	SetIgnore: (Instances: { Instance }) -> ()
}
export type InternalModule = PublicModule & {
	_update: (DeltaTime: number) -> (),
	_removeParticle: (ParticleId: number) -> (),
	_removeSplatter: (Splatter: MeshPart?) -> (),
	_createSplatter: (Position: Vector3, Normal: Vector3, Force: number, SplatterWidth: number?) -> (),
	_createSplash: (Position: Vector3, Normal: Vector3) -> (),
	_lastUpdate: number,
	_activeParticles: {ParticleObject},
	_activeSplatters: {[MeshPart]: number},
	_splatCount: number
}

-- Constants
local MAX_ACTIVE_PARTICLES = 25
local MAX_ACTIVE_SPLATTERS = 60
local SPLASH_SUPPRESS_THRESHOLD = 12
local MAX_DT = 1 / 20 -- 50ms ceiling, prevents death spiral
local SOUND_FALLBACK_LIFETIME = 4 -- release a pooled sound point by this long even if Sound.Ended never fires
local SWEEP_INTERVAL = 3 -- seconds between orphan-reclaim sweeps of the Container

local MESH_PARAMS = {
	CollisionFidelity = Enum.CollisionFidelity.Box,
	RenderFidelity = Enum.RenderFidelity.Performance,
	FluidFidelity = Enum.FluidFidelity.UseCollisionGeometry
}

-- Services
local AssetService = game:GetService("AssetService")
local TweenService = game:GetService("TweenService")
local SoundService = game:GetService("SoundService")
local RunService = game:GetService("RunService")

-- Modules
local Settings = require(script.Settings)
local Pools = require(script.Pools)

-- Raycast params
local rayParams = RaycastParams.new()
rayParams.ExcludeInstances = Settings.IgnoreInstances :: {Instance}
rayParams.RespectCanCollide = true
rayParams.IgnoreWater = true

-- Safely remove an item.
local function Remove(Item: Instance?): ()
	if Item then Item:Destroy() end
end

-- Create a sphere meshpart.
local function CreateSphere(Half: boolean?): MeshPart

	local mesh = AssetService:CreateEditableMesh({FixedSize = false})

	local latitudeSteps = Settings.MeshQuality
	local longitudeSteps = latitudeSteps * 2

	local data = {}

	for latitude = 0, latitudeSteps do

		local v = latitude / latitudeSteps
		local theta = v * math.pi

		if Half then
			theta = v * (math.pi / 2)
		end

		local row = {}

		for longitude = 0, longitudeSteps do

			local u = longitude / longitudeSteps
			local phi = u * math.pi * 2

			local x = math.sin(theta) * math.cos(phi)
			local y = math.cos(theta)
			local z = math.sin(theta) * math.sin(phi)

			local position = Vector3.new(x, y, z)
			local normal = position.Unit

			local vertexId = mesh:AddVertex(position)
			local normalId = mesh:AddNormal(normal)
			local uvId = mesh:AddUV(Vector2.new(u, v))

			row[longitude] = {
				Vertex = vertexId,
				Normal = normalId,
				UV = uvId
			}
		end

		data[latitude] = row
	end

	for latitude = 0, latitudeSteps - 1 do
		for lonitude = 0, longitudeSteps - 1 do

			local dataA = data[latitude][lonitude]
			local dataB = data[latitude + 1][lonitude]
			local dataC = data[latitude + 1][lonitude + 1]
			local dataD = data[latitude][lonitude + 1]

			local faceA = mesh:AddTriangle(dataA.Vertex, dataC.Vertex, dataB.Vertex)
			local faceB = mesh:AddTriangle(dataA.Vertex, dataD.Vertex, dataC.Vertex)

			mesh:SetFaceUVs(faceA, {dataA.UV, dataC.UV, dataB.UV})
			mesh:SetFaceUVs(faceB, {dataA.UV, dataD.UV, dataC.UV})

			mesh:SetFaceNormals(faceA, {dataA.Normal, dataC.Normal, dataB.Normal})
			mesh:SetFaceNormals(faceB, {dataA.Normal, dataD.Normal, dataC.Normal})
		end
	end

	local _, dataModel = AssetService:CreateDataModelContentAsync(Content.fromObject(mesh))
	mesh:Destroy()

	local meshpart = AssetService:CreateMeshPartAsync(dataModel, MESH_PARAMS)
	meshpart:ApplyMesh(meshpart)
	meshpart.Transparency = Settings.BloodTransparency
	meshpart.Reflectance = Settings.BloodReflectance
	meshpart.Material = Settings.BloodMaterial
	meshpart.Color = Settings.BloodColor
	meshpart.EnableFluidForces = false
	meshpart.CanCollide = false
	meshpart.CanQuery = false
	meshpart.CanTouch = false
	meshpart.Anchored = true
	meshpart.CastShadow = false

	return meshpart
end

-- Create a sound point.
local function CreateSoundPoint(): Attachment

	local point = Instance.new("Attachment")
	point.Name = script.Name.. "Point"

	local sound = Instance.new("Sound")
	sound.Volume = Settings.SplatterVolume
	sound.RollOffMaxDistance = Settings.SplatterRange
	sound.RollOffMinDistance = Settings.SplatterRange / 3
	sound.Parent = point

	return point
end

-- Object pools
local ParticlePool = Pools.new(CreateSphere(false), Settings.ParticlePoolSize)
local SplatterPool = Pools.new(CreateSphere(true), Settings.SplatterPoolSize)
local SoundPool = Pools.new(CreateSoundPoint(), Settings.SoundPoolSize)

-- Cache blood sounds
for _, soundId in Settings.SplatterSounds do

	local sound = Instance.new("Sound")
	sound.SoundId = `rbxassetid://{soundId}`
	sound.Name = "Blood Sound Cache"
end

-- Module
local Module = {} :: InternalModule
Module._activeParticles = {}
Module._activeSplatters = {}
Module._splatCount = 0
Module._lastUpdate = time()
Module._sweepNext = 0

--[[
	Creates a new blood drop.
	-----------------------------------------------
	<strong># Position: </strong> <em>The origin of the blood.</em>
	<strong># Direction: </strong> <em>The direction of the blood.</em>
	<strong># Force: </strong> <em>The speed of the blood.</em>
]]
function Module.new(Position: Vector3, Direction: Vector3, Force: number, Options: BloodOptions?): ()

	if #Module._activeParticles >= MAX_ACTIVE_PARTICLES then
		return
	end

	local lifetimeRange = Settings.ParticleLifetime
	local widthRange = Settings.ParticleWidth

	local lifetime = Random.new():NextNumber(
		lifetimeRange.Min, lifetimeRange.Max
	)
	local width = (Options and Options.ParticleWidth) or Random.new():NextNumber(
		widthRange.Min, widthRange.Max
	)

	local transform = CFrame.new(Position, Position + Direction)

	table.insert(Module._activeParticles, {
		Lifetime = time() + lifetime,
		Transform = transform,
		Velocity = transform.LookVector * Force,
		MeshPart = nil,
		Width = width,
		SplatterWidth = Options and Options.SplatterWidth,
		Splashed = false
	})
end

--[[
	Destroys all the blood.
]]
function Module.Clean(): ()
	for _, data in Module._activeParticles do
		data.Lifetime = 0
	end
	for splatter, _ in Module._activeSplatters do
		Module._activeSplatters[splatter] = 0
	end
end

--[[
	Replaces the droplet raycast ignore list. Live — affects every droplet from the next frame on.
	rayParams.ExcludeInstances is captured once at load, so the array must be reassigned on the
	RaycastParams (mutating Settings.IgnoreInstances in place does nothing). Pass {} to clear.
]]
function Module.SetIgnore(Instances: { Instance }): ()
	Settings.IgnoreInstances = Instances
	rayParams.ExcludeInstances = Instances
end

-- Update the module.
function Module._update(DeltaTime: number): ()

	-- Fix A: clamp DeltaTime to prevent death spiral
	DeltaTime = math.min(DeltaTime, MAX_DT)

	local currentTime = time()

	local updatedParticles: {Instance} = {}
	local updatedTransforms: {CFrame} = {}

	local gravity = Settings.Gravity
	local squishFactor = 60 / Settings.ParticleSquish
	local sounds = Settings.SplatterSounds
	local container = Settings.Container

	local wind = (Settings.WindEnabled and workspace.GlobalWind or Vector3.zero)
		* Settings.WindInfluence

	-- Fix B: swap-remove eviction (O(1) per remove vs O(n))
	local particles = Module._activeParticles
	local pCount = #particles
	while pCount > MAX_ACTIVE_PARTICLES do
		local meshpart = particles[1].MeshPart
		if meshpart then
			ParticlePool:Release(meshpart)
		end
		particles[1] = particles[pCount]
		particles[pCount] = nil
		pCount -= 1
	end

	-- Fix D: batch splatter eviction once per frame, not per-hit
	local splatCount = Module._splatCount
	while splatCount > MAX_ACTIVE_SPLATTERS do
		local oldest, oldestTime = nil :: MeshPart?, math.huge
		for splatter, lifetime in Module._activeSplatters do
			if lifetime < oldestTime then
				oldest = splatter
				oldestTime = lifetime
			end
		end

		if oldest then
			SplatterPool:Release(oldest)
			Module._activeSplatters[oldest] = nil
			splatCount -= 1
		else
			break
		end
	end
	Module._splatCount = splatCount

	-- Fix C: collect hits for deferred splatter creation + reverse-order removal
	local hitResults: {{Position: Vector3, Normal: Vector3, Force: number, Splashed: boolean, SplatterWidth: number?}} = {}
	local removingParticles: {number} = {}

	debug.profilebegin("Blood::particles")
	for particleId, data in particles do

		if currentTime > data.Lifetime then
			table.insert(removingParticles, particleId)
			continue
		end

		local velocity = data.Velocity
		local transform = data.Transform

		local meshpart = data.MeshPart or ParticlePool:Get()
		if not meshpart then
			continue
		end

		velocity += (gravity + wind) * DeltaTime

		local squish = velocity.Magnitude / squishFactor
		local width = data.Width / 2

		local rayTarget = transform.Position + velocity * DeltaTime
		local raycast = workspace:Raycast(transform.Position, rayTarget - transform.Position, rayParams)

		meshpart.Size = Vector3.new(width, width, width + squish)
		meshpart.Parent = container

		table.insert(updatedParticles, meshpart)
		table.insert(updatedTransforms, CFrame.new(rayTarget, rayTarget - velocity)
			* CFrame.new(0, 0, -meshpart.Size.Z / 2))

		if raycast then

			ParticlePool:Release(meshpart)
			-- clear the particle's stored ref too: the deferred removal below ALSO releases
			-- particles[id].MeshPart, and if a later droplet in this same loop already re-pooled this
			-- exact MeshPart (Get popped it off the free list), that second release would yank the new
			-- droplet's part — leaving it parented but tracked by nothing = a permanent Container orphan.
			data.MeshPart = nil

			local point = SoundPool:Get()
			if point then

				point.WorldPosition = raycast.Position
				point.Parent = container

				local sound = point:FindFirstChild("Sound") :: Sound
				sound.SoundId = `rbxassetid://{sounds[math.random(#sounds)]}`
				sound.PlaybackSpeed = Random.new():NextNumber(0.9, 1.1)
				sound:Play()

				-- release on Ended OR a fallback timeout, whichever fires first. Sound.Ended does NOT
				-- fire if the sound fails to load (the splatter sounds are never preloaded), which
				-- otherwise leaks the pooled sound point + its Attachment forever. The `released` guard
				-- keeps the pair idempotent and stops a stale fallback from releasing the point after a
				-- later splatter has reused it.
				local released = false
				local function releasePoint(): ()
					if released then
						return
					end

					released = true
					SoundPool:Release(point)
				end

				sound.Ended:Once(releasePoint)
				task.delay(SOUND_FALLBACK_LIFETIME, releasePoint)
			end

			-- defer splatter/splash creation until after particle loop
			table.insert(hitResults, {
				Position = raycast.Position,
				Normal = raycast.Normal,
				Force = math.abs(data.Velocity.Magnitude) / 2.5,
				Splashed = data.Splashed,
				SplatterWidth = data.SplatterWidth
			})

			table.insert(removingParticles, particleId)
			continue
		else

			particles[particleId].MeshPart = meshpart
			particles[particleId].Velocity = velocity
			particles[particleId].Transform = CFrame.new(rayTarget, rayTarget + velocity)
		end
	end
	debug.profileend()

	-- Fix C: remove particles in reverse index order so shifts don't corrupt
	debug.profilebegin("Blood::cleanup")
	table.sort(removingParticles, function(a, b) return a > b end)
	for _, particleId in removingParticles do
		if particleId <= #particles then
			local meshpart = particles[particleId].MeshPart
			if meshpart then
				ParticlePool:Release(meshpart)
			end
			local last = #particles
			if particleId < last then
				particles[particleId] = particles[last]
			end
			particles[last] = nil
		end
	end
	debug.profileend()

	debug.profilebegin("Blood::bulkMove")
	workspace:BulkMoveTo(updatedParticles, updatedTransforms)
	debug.profileend()

	-- process deferred splatter/splash creation outside particle loop
	debug.profilebegin("Blood::splatters")
	for _, hit in hitResults do
		if hit.Splashed then
			Module._createSplash(hit.Position, hit.Normal)
		else
			Module._createSplatter(hit.Position, hit.Normal, hit.Force, hit.SplatterWidth)
		end
	end

	for splatter, Lifetime in Module._activeSplatters do
		if currentTime > Lifetime then
			Module._removeSplatter(splatter)
			continue
		end
	end
	debug.profileend()

	-- safety sweep (throttled): reclaim any pooled MeshPart left in the Container that NO active
	-- particle or splatter tracks — a self-heal for orphans from any edge in the pooled lifecycle so
	-- they can never accumulate forever in workspace.Blood. Creation is synchronous within a frame, so
	-- nothing here is mid-transition (a just-made part is already tracked by the time the sweep runs).
	if currentTime >= Module._sweepNext then
		Module._sweepNext = currentTime + SWEEP_INTERVAL

		local tracked = {}
		for _, particle in particles do
			if particle.MeshPart then
				tracked[particle.MeshPart] = true
			end
		end
		for splatter in Module._activeSplatters do
			tracked[splatter] = true
		end

		for _, child in container:GetChildren() do
			if child:IsA("MeshPart") and not tracked[child] then
				-- return it to its pool; also force the parent off in case the pooled object was left
				-- free-but-parented (Pool:Release no-ops on an already-free object, so it wouldn't
				-- otherwise leave the Container)
				if child.Name == "Splatter" or child.Name == "Splash" then
					SplatterPool:Release(child)
				else
					ParticlePool:Release(child)
				end
				child.Parent = nil
			end
		end
	end
end

-- Remove a active particle object.
function Module._removeParticle(ParticleId: number): ()

	local particles = Module._activeParticles
	if not particles[ParticleId] then
		return
	end

	local meshpart = particles[ParticleId].MeshPart
	if meshpart then
		ParticlePool:Release(meshpart)
	end

	-- swap-remove: O(1) instead of O(n)
	local last = #particles
	if ParticleId < last then
		particles[ParticleId] = particles[last]
	end
	particles[last] = nil
end

-- Remove a active splatter object.
function Module._removeSplatter(Splatter: MeshPart?): ()

	-- only release + decrement a still-TRACKED splatter, so a double-remove can't drift _splatCount
	-- below the real key count (the mirror of the count-a-new-key-only guard in _createSplatter)
	if not Splatter or Module._activeSplatters[Splatter] == nil then
		return
	end

	SplatterPool:Release(Splatter)
	Module._activeSplatters[Splatter] = nil
	Module._splatCount -= 1
end

-- Create a new splatter.
function Module._createSplatter(Position: Vector3, Normal: Vector3, Force: number, SplatterWidth: number?): ()

	-- Fix E: cap check for splash particles
	if Settings.SplashingEnabled and #Module._activeParticles < SPLASH_SUPPRESS_THRESHOLD then

		local splashes = Settings.SplashAmount
		splashes = math.random(splashes.Min, splashes.Max)

		for _ = 1, splashes do

			if #Module._activeParticles >= MAX_ACTIVE_PARTICLES then
				break
			end

			local direction = CFrame.new(
				Position, Position + Vector3.new(
					Random.new():NextNumber(-1, 1),
					Normal.Y, Random.new():NextNumber(-1, 1)
				)
			).LookVector
			local transform = CFrame.new(Position, Position + direction)

			local lifetime = Settings.ParticleLifetime
			local width = Settings.ParticleWidth

			lifetime = Random.new():NextNumber(
				lifetime.Min, lifetime.Max
			)
			width = Random.new():NextNumber(
				width.Min, width.Max
			)

			table.insert(Module._activeParticles, {
				Lifetime = time() + lifetime,
				Transform = transform,
				Velocity = transform.LookVector * Force,
				MeshPart = nil,
				Width = width,
				Splashed = true
			})
		end
	end

	if Module._splatCount >= MAX_ACTIVE_SPLATTERS then
		return
	end

	local transform = CFrame.new(Position, Position + Normal)

	local splatterRange = Settings.SplatterWidth
	local endWidth = SplatterWidth or Random.new():NextNumber(splatterRange.Min, splatterRange.Max)
	local startWidth = endWidth * 0.8

	local splatter = SplatterPool:Get(true)
	if not splatter then
		return
	end

	splatter.CFrame = transform * CFrame.Angles(math.rad(-90), 0, 0)
	splatter.Size = Vector3.new(startWidth, endWidth * 0.2, startWidth)
	splatter.Name = "Splatter"
	splatter.Parent = Settings.Container

	local tween = TweenService:Create(
		splatter,
		Settings.SplatterTweenInfo,
		{Size = Vector3.new(endWidth, endWidth * 0.2, endWidth)}
	)
	tween:Play()

	task.delay(tween.TweenInfo.Time, Remove, tween)

	local lifetime = Settings.SplatterLifetime
	lifetime = Random.new():NextNumber(
		lifetime.Min, lifetime.Max
	)

	-- count a NEW key only: under pool pressure SplatterPool:Get(true) hands back an already-tracked
	-- splatter, so a blind +1 drifts _splatCount above the real key count → the eviction loop later
	-- over-drains _activeSplatters to empty while _splatCount stays > MAX, orphaning Container MeshParts.
	if Module._activeSplatters[splatter] == nil then
		Module._splatCount += 1
	end
	Module._activeSplatters[splatter] = time() + lifetime

	if Settings.DrippingEnabled then

		local angle = transform.LookVector:Dot(Vector3.yAxis) * 90
		if angle < -Settings.DripSurfaceAngle then

			local drips = Settings.DrippingAmount
			drips = math.random(drips.Min, drips.Max)

			task.spawn(function(): ()
				for _ = 1, (drips :: number) do

					-- Fix E: cap check in drip creation
					if #Module._activeParticles >= MAX_ACTIVE_PARTICLES then
						break
					end

					local dripTime = Settings.DripTime

					local dripLifetime = Settings.ParticleLifetime
					local width = Settings.ParticleWidth
					local dripTime = Settings.DripTime

					dripLifetime = Random.new():NextNumber(
						dripLifetime.Min, dripLifetime.Max
					)
					width = Random.new():NextNumber(
						width.Min, width.Max
					)
					dripTime = Random.new():NextNumber(
						dripTime.Min, dripTime.Max
					)

					task.wait(dripTime)

					if #Module._activeParticles >= MAX_ACTIVE_PARTICLES then
						break
					end

					local dripTransform = CFrame.new(
						transform.Position,
						transform.Position - Vector3.yAxis
					)

					table.insert(Module._activeParticles, {
						Lifetime = time() + dripLifetime,
						Transform = dripTransform,
						Velocity = dripTransform.LookVector * Force,
						MeshPart = nil,
						Width = width,
						Splashed = false
					})
				end
			end)
		end
	end
end

-- Create a new splash
function Module._createSplash(Position: Vector3, Normal: Vector3): ()

	if Module._splatCount >= MAX_ACTIVE_SPLATTERS then
		return
	end

	local transform = CFrame.new(Position, Position + Normal)

	local endWidth = Settings.SplashWidth
	endWidth = Random.new():NextNumber(endWidth.Min, endWidth.Max)
	local startWidth = endWidth * 0.8

	local splatter = SplatterPool:Get(true)
	if not splatter then
		return
	end

	splatter.CFrame = transform * CFrame.Angles(math.rad(-90), 0, 0)
	splatter.Size = Vector3.new(startWidth, endWidth * 0.2, startWidth)
	splatter.Name = "Splash"
	splatter.Parent = Settings.Container

	local tween = TweenService:Create(
		splatter,
		Settings.SplatterTweenInfo,
		{Size = Vector3.new(endWidth, endWidth * 0.2, endWidth)}
	)
	tween:Play()

	task.delay(tween.TweenInfo.Time, Remove, tween)

	local lifetime = Settings.SplatterLifetime
	lifetime = Random.new():NextNumber(
		lifetime.Min, lifetime.Max
	)

	-- count a NEW key only: under pool pressure SplatterPool:Get(true) hands back an already-tracked
	-- splatter, so a blind +1 drifts _splatCount above the real key count → the eviction loop later
	-- over-drains _activeSplatters to empty while _splatCount stays > MAX, orphaning Container MeshParts.
	if Module._activeSplatters[splatter] == nil then
		Module._splatCount += 1
	end
	Module._activeSplatters[splatter] = time() + lifetime
end

-- Debug counters (read via MicroProfiler custom labels)
local DBG_LOG_INTERVAL = 2
local dbgNextLog = 0

-- Update event.
RunService.PreRender:Connect(function(): ()

	local currentTime = time()
	local deltaTime = currentTime - Module._lastUpdate
	Module._lastUpdate = time()

	debug.profilebegin("Blood::_update")
	Module._update(deltaTime)
	debug.profileend()

	if currentTime >= dbgNextLog then
		dbgNextLog = currentTime + DBG_LOG_INTERVAL
		local pCount = #Module._activeParticles
		local sCount = Module._splatCount
		if pCount > 0 or sCount > 0 then
			warn(("[Blood] particles=%d  splatters=%d"):format(pCount, sCount))
		end
	end
end)

return Module :: PublicModule
