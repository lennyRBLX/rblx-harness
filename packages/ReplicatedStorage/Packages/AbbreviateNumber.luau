local ACRONYMS = {
	"K","M","B","T","Qa","Qi","Sx","Sp","Oc","No",
	"Dd","Ud","Dd","Td","Qad","Qid","Sxd","Spd","Ocd","Nod",
	"Vg","Uvg","Dvg","Tvg","Qavg","Qivg","Sxvg","Spvg","Ocvg"
}

local POWERS, MULTIPLIERS = table.create(#ACRONYMS), {}
local Initialized = false

return function(value, asAbbreviation)
	if not Initialized then
		Initialized = true
		
		for i = 1, #ACRONYMS do
			POWERS[i] = 1000 ^ i
			MULTIPLIERS[ACRONYMS[i]] = POWERS[i]
		end
	end

	if asAbbreviation then
		local s = tostring(value)
		s = s:match("^%s*(.-)%s*$")
		s = s:gsub(",", ""):gsub("_", "")

		local numStr, suffix = s:match("^([%d.]+)(%a)$")
		if not numStr then
			return nil
		end

		local n = tonumber(numStr)
		if not n then
			return nil
		end

		if suffix == "" then
			return n
		end

		local normalizedSuffix = suffix:sub(1,1):upper() .. suffix:sub(2):lower()
		local mult = MULTIPLIERS[normalizedSuffix]
		if not mult then
			return nil
		end

		return n * mult
	end

	-- formatting branch: requires number
	local num = tonumber(value)
	if not num then
		return tostring(value)
	end

	local absolute = math.abs(num)
	if absolute < 1000 then
		return tostring(num)
	end

	local pow = math.min(math.floor(math.log10(absolute) / 3), #ACRONYMS)
	local abbreviated = (math.floor(absolute / POWERS[pow] * 100) / 100) * math.sign(num)
	return tostring(abbreviated) .. ACRONYMS[pow]:lower()
end
