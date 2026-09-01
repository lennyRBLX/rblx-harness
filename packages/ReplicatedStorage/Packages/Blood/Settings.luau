-- Container
local container = Instance.new("Folder")
container.Name = "Blood"
container.Parent = workspace

-- Module
return {

	-- ROOT
	Container = container, -- The folder that the blood gets parented to.

	-- RAYCASTING
	Gravity = Vector3.new(0, -100, 0), -- The gravity of the blood.
	IgnoreInstances = {}, -- Instances the raycast will ignore.

	-- WIND
	WindEnabled = true, -- Enables if the wind affects the blood.
	WindInfluence = Vector3.new(1, 1, 1), -- Multiplier influence for the wind.

	-- MESHES
	MeshQuality = 8, -- The subdivision quality of the blood meshes.

	-- VISUALS
	BloodColor = Color3.fromRGB(9, 12, 15), -- The color of the blood.
	BloodTransparency = 0.5, -- The transparency of the blood.
	BloodMaterial = Enum.Material.Glass, -- The material of the blood.
	BloodReflectance = 0.55, -- The reflectance of the blood.

	-- PARTICLES
	ParticleSquish = 2, -- The squish amount of the blood particle.
	ParticleWidth = {Min = 0.15, Max = 0.25}, -- The width of the blood particle.

	-- SPLATTERS
	SplatterWidth = {Min = 0.6, Max = 0.9}, -- The width of the blood splatter.
	SplatterTweenInfo = TweenInfo.new(0.15, Enum.EasingStyle.Cubic), -- The tween info of the splatters impact.

	-- SPLASHING
	SplashAmount = {Min = 0, Max = 2}, -- The amount of blood that splashes from impact.
	SplashingEnabled = true, -- Enables if blood should create smaller blood splashes.
	SplashWidth = {Min = 0.2, Max = 0.3}, -- The width of the blood splashes.

	-- DRIPPING
	DrippingAmount = {Min = 0, Max = 3}, -- The amount of drips a splatter can create.
	DripSurfaceAngle = 45, -- The angle at which counts as a ceiling.
	DripTime = {Min = 0.5, Max = 2.5}, -- The time inbetween each drip.
	DrippingEnabled = true, -- Enables if blood can drip from ceilings.

	-- SOUNDS
	SplatterSounds = { -- The sound ids of the splatter impacts.
		130790775111900, 97897441958279,
		138302808424317, 131915869032782,
		73237056281539, 132746561421935,
		108641438891078
	},
	SplatterRange = 30, -- How far the sound can travel.
	SplatterVolume = 0.05, -- How loud the sound is.

	-- LIFETIMES
	ParticleLifetime = {Min = 5, Max = 6}, -- How long a blood particle can exist for.
	SplatterLifetime = {Min = 10, Max = 15}, -- How long a blood splatter can exist for.

	-- OBJECT POOLS
	ParticlePoolSize = 250, -- The size of the object pool for particles.
	SplatterPoolSize = 750, -- The size of the object pool for splatters.
	SoundPoolSize = 35 -- The size of the object pool for sounds.
}
