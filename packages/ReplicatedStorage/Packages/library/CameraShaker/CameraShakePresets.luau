-- Camera Shake Presets
-- Crazyman32
-- February 26, 2018

--[[
	
	CameraShakePresets.Bump
	CameraShakePresets.Explosion
	CameraShakePresets.Earthquake
	CameraShakePresets.BadTrip
	CameraShakePresets.HandheldCamera
	CameraShakePresets.Vibration
	CameraShakePresets.RoughDriving
	
--]]



local CameraShakeInstance = require(script.Parent.CameraShakeInstance)

local CameraShakePresets = {
	
	
	-- A high-magnitude, short, yet smooth shake.
	-- Should happen once.
	Bump = function()
		local c = CameraShakeInstance.new(2.5, 4, 0.1, 0.75)
		c.PositionInfluence = Vector3.new(0.15, 0.15, 0.15)
		c.RotationInfluence = Vector3.new(1, 1, 1)
		return c
	end;

	BigBump = function()
		local c = CameraShakeInstance.new(2.5, 4, 0.1, 0.75)
		c.PositionInfluence = Vector3.new(0.8, 0.8, 0.8)
		c.RotationInfluence = Vector3.new(1, 1, 1)
		return c
	end;
	
	SmallBump = function()
		local c = CameraShakeInstance.new(2.5, 4, 0.1, 0.75)
		c.PositionInfluence = Vector3.new(0.01, 0.01, 0.01)
		c.RotationInfluence = Vector3.new(.5, .5, .5)
		return c
	end;
	
	SmallestBump = function()
		local c = CameraShakeInstance.new(1.25, 2, 0.05, 0.405)
		c.PositionInfluence = Vector3.new(0.005, 0.005, 0.005)
		c.RotationInfluence = Vector3.new(.25, .25, .25)
		return c
	end;
	
	Loop = function()
		local c = CameraShakeInstance.new(.5, 1, 0.05, 0.35)
		c.PositionInfluence = Vector3.new(0.01, 0.01, 0.01)
		c.RotationInfluence = Vector3.new(.25, .25, .25)
		return c
	end;
	
	-- An intense and rough shake.
	-- Should happen once.
	Explosion = function()
		local c = CameraShakeInstance.new(5, 10, 0, 1.5)
		c.PositionInfluence = Vector3.new(0.25, 0.25, 0.25)
		c.RotationInfluence = Vector3.new(4, 1, 1)
		return c
	end;
	
	BumpRemaked = function()
		local c = CameraShakeInstance.new(2, 5, 0, 1)
		c.PositionInfluence = Vector3.new(0.2, 0.2, 0.2)
		c.RotationInfluence = Vector3.new(3, 1, 1)
		return c
	end;
		
	BigExplosion = function()
		local c = CameraShakeInstance.new(20, 40, 0, 2)
		c.PositionInfluence = Vector3.new(0.55, 0.55, 0.55)
		c.RotationInfluence = Vector3.new(5, 2, 2)
		return c
	end;
	
	ReallyBigExplosion = function()
		local c = CameraShakeInstance.new(30, 50, 0, 1.5)
		c.PositionInfluence = Vector3.new(1, 1, 1)
		c.RotationInfluence = Vector3.new(5, 2, 2)
		return c
	end;
	
	SmallExplosion = function()
		local c = CameraShakeInstance.new(5, 10, 0, 1.5)
		c.PositionInfluence = Vector3.new(0.15, 0.15, 0.15)
		c.RotationInfluence = Vector3.new(4, 1, 1)
		return c
	end;
	
	ExplosionNormal = function()
		local c = CameraShakeInstance.new(5, 10, 0, 1.5)
		c.PositionInfluence = Vector3.new(3,3,3)
		c.RotationInfluence = Vector3.new(4, 1, 1)
		return c
	end;
	-- A continuous, rough shake
	-- Sustained.
	Earthquake = function()
		local c = CameraShakeInstance.new(0.6, 3.5, 2, 10)
		c.PositionInfluence = Vector3.new(0.25, 0.25, 0.25)
		c.RotationInfluence = Vector3.new(1, 1, 4)
		return c
	end;
	
	
	-- A bizarre shake with a very high magnitude and low roughness.
	-- Sustained.
	BadTrip = function()
		local c = CameraShakeInstance.new(10, 0.15, 5, 10)
		c.PositionInfluence = Vector3.new(0, 0, 0.15)
		c.RotationInfluence = Vector3.new(2, 1, 4)
		return c
	end;
	
	
	-- A subtle, slow shake.
	-- Sustained.
	HandheldCamera = function()
		local c = CameraShakeInstance.new(1, 0.25, 5, 10)
		c.PositionInfluence = Vector3.new(0, 0, 0)
		c.RotationInfluence = Vector3.new(1, 0.5, 0.5)
		return c
	end;
	
	
	-- A very rough, yet low magnitude shake.
	-- Sustained.
	Vibration = function()
		local c = CameraShakeInstance.new(0.4, 20, 2, 2)
		c.PositionInfluence = Vector3.new(0, 0.15, 0)
		c.RotationInfluence = Vector3.new(1.25, 0, 4)
		return c
	end;
	
	
	-- A slightly rough, medium magnitude shake.
	-- Sustained.
	RoughDriving = function()
		local c = CameraShakeInstance.new(1, 2, 1, 1)
		c.PositionInfluence = Vector3.new(0, 0, 0)
		c.RotationInfluence = Vector3.new(1, 1, 1)
		return c
	end;
	
	
}


return setmetatable({}, {
	__index = function(t, i)
		local f = CameraShakePresets[i]
		if (type(f) == "function") then
			return f()
		end
		error("No preset found with index \"" .. i .. "\"")
	end;
})