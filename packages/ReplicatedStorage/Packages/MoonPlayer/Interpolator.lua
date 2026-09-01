local Interpolator = {}

local CONSTANT_INTERPS = {
	["Instance"] = true,
	["boolean"] = true,
	["nil"] = true,
}

local function lerp(a: any, b: any, t: number): any
	if type(a) == "number" then
		return a + ((b - a) * t)
	else
		if type(a) == "string" then return b end
		return (a :: any):Lerp(b, t)
	end
end

function Interpolator.get(value)
	if typeof(value) == "ColorSequence" then
		return function(start: ColorSequence, goal: ColorSequence, t: number)
			local v = lerp(start.Keypoints[1].Value, goal.Keypoints[1].Value, t)
			return ColorSequence.new(v)
		end
	elseif typeof(value) == "NumberSequence" then
		return function(start: NumberSequence, goal: NumberSequence, t: number)
			local v = lerp(start.Keypoints[1].Value, goal.Keypoints[1].Value, t)
			return NumberSequence.new(v)
		end
	elseif typeof(value) == "NumberRange" then
		return function(start: NumberRange, goal: NumberRange, t: number)
			local v = lerp(start.Min, goal.Min, t)
			return NumberRange.new(v)
		end
	elseif CONSTANT_INTERPS[typeof(value)] then
		return function(start: any, goal: any, t: number)
			return if t >= 1 then goal else start
		end
	end

	return lerp
end

return Interpolator