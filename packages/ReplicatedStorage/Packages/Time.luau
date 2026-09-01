--[[
Time:
	Handles anything related to tick based operations.
]]

local TIME_UNIT_COMPACT_SUFFIXES = {
	["Eon"] = "eon", ["Eons"] = "eon",
	["Millennium"] = "mil", ["Millennia"] = "mil",
	["Century"] = "cen", ["Centuries"] = "cen",
	["Decade"] = "dec", ["Decades"] = "dec",
	["Year"] = "y", ["Years"] = "y",
	["Month"] = "mo", ["Months"] = "mo",
	["Day"] = "d", ["Days"] = "d",
	["Hour"] = "h", ["Hours"] = "h",
	["Minute"] = "m", ["Minutes"] = "m",
	["Second"] = "s", ["Seconds"] = "s"
}

local m = {}

-- functions
function m:GetSecondsBetween(a, b)
	assert(typeof(a) == "number" and typeof(b) == "number", "Time.GetSecondsBetween | a and b must be a number")
	return (a - b) / 60
end

function m:GetMinutesBetween(a, b)
	assert(typeof(a) == "number" and typeof(b) == "number", "Time.GetMinutesBetween | a and b must be a number")
	return (a - b) / 60
end

function m:GetHoursBetween(a, b)
	assert(typeof(a) == "number" and typeof(b) == "number", "Time.GetHoursBetween | a and b must be a number")
	return self:GetMinutesBetween(a, b) / 60
end

function m:GetDaysBetween(a, b)
	assert(typeof(a) == "number" and typeof(b) == "number", "Time.GetDaysBetween | a and b must be a number")
	return self:GetHoursBetween(a, b) / 24
end

function m:MinutesToSeconds(amount)
	assert(typeof(amount) == "number", "Time.MinutesToSeconds | amount must be a number")
	return amount * 60
end

function m:HoursToSeconds(amount)
	assert(typeof(amount) == "number", "Time.HoursToSeconds | amount must be a number")
	return self:MinutesToSeconds(amount * 60)
end

function m:DaysToSeconds(amount)
	assert(typeof(amount) == "number", "Time.DaysToSeconds | amount must be a number")
	return self:HoursToSeconds(amount * 24)
end

function m:SecondsToMinutes(amount)
	assert(typeof(amount) == "number", "Time.SecondsToMinutes | amount must be a number")
	return amount / 60
end

function m:SecondsToHours(amount)
	assert(typeof(amount) == "number", "Time.SecondsToHours | amount must be a number")
	return self:SecondsToMinutes(amount / 60)
end

function m:SecondsToDays(amount)
	assert(typeof(amount) == "number", "Time.SecondsToDays | amount must be a number")
	return self:SecondsToHours(amount / 24)
end

function m:SecondsToTable(seconds)
	local minutes = math.floor(seconds / 60)
	local remainingSeconds = seconds % 60

	local hours = math.floor(minutes / 60)
	local remainingMinutes = minutes % 60

	local days = math.floor(hours / 24)
	local remainingHours = hours % 24

	local years = math.floor(days / 365)
	local remainingDays = days % 365

	local months = math.floor(remainingDays / 30)
	local finalDays = remainingDays % 30

	local decades = math.floor(years / 10)
	local remainingYears = years % 10

	local centuries = math.floor(decades / 10)
	local remainingDecades = decades % 10

	local millennia = math.floor(centuries / 10)
	local remainingCenturies = centuries % 10

	local eons = math.floor(millennia / 10)
	local remainingMillennia = millennia % 10

	local result = {}
	local function timeUnit(value, singularName, pluralName, occupies, overwriteOccupy)
		return {
			Type = value == 1 and singularName or pluralName,
			Value = value ~= 0 and value or nil,
			Occupies = occupies or 1,
			Overwrite = overwriteOccupy
		}
	end

	table.insert(result, timeUnit(eons, "Eon", "Eons", 1))
	table.insert(result, timeUnit(remainingMillennia, "Millennium", "Millennia", 1))
	table.insert(result, timeUnit(remainingCenturies, "Century", "Centuries", 1))
	table.insert(result, timeUnit(remainingDecades, "Decade", "Decades", 1))
	table.insert(result, timeUnit(remainingYears, "Year", "Years", 1))
	table.insert(result, timeUnit(months, "Month", "Months", 2))
	table.insert(result, timeUnit(finalDays, "Day", "Days", 2))
	table.insert(result, timeUnit(remainingHours, "Hour", "Hours", 1))
	table.insert(result, timeUnit(remainingMinutes, "Minute", "Minutes", 2))
	table.insert(result, timeUnit(remainingSeconds, "Second", "Seconds", 2, true))
	return result
end

function m:SecondsToPrettyText(seconds, includeAfter: boolean?)
	local units = self:SecondsToTable(seconds)
	local result, count, skipping = "", 0, true

	for i, unit in ipairs(units) do
		local value = unit.Value
		if not value and (not includeAfter or skipping) then
			continue
		end

		value = value or 0
		skipping = false

		if i == #units then
			result = ("%s and %d %s"):format(result, value, unit.Type)
		elseif i == #units - 1 then
			result = ("%s%d %s"):format(result, value, unit.Type)
		else
			result = ("%s%d %s, "):format(result, value, unit.Type)
		end

		count += 1
	end

	return (count ~= 1 and result) or result:gsub(" and ", ""):gsub(", $", "")
end

function m:SecondsToCompactText(seconds, maxUnits, includeAfter: boolean?)
	local units = self:SecondsToTable(seconds)
	local result = {}

	local firstUnitIndex = nil
	for i, unit in ipairs(units) do
		if unit.Value and unit.Value > 0 then
			firstUnitIndex = i
			break
		end
	end
	
	if not firstUnitIndex then
		return "0s"
	end

	local skipping = true
	for i = firstUnitIndex, math.min(maxUnits and (firstUnitIndex + maxUnits - 1) or #units, #units) do
		local unit = units[i]
		if not unit.Value and (not includeAfter or skipping) then
			continue
		end
		
		skipping = false
		
		local suffix = TIME_UNIT_COMPACT_SUFFIXES[unit.Type]
		table.insert(result, ("%d%s"):format(unit.Value or 0, suffix))
	end

	return #result > 0 and table.concat(result, " ") or "0s"
end

function m:SecondsToColonText(seconds, minUnits)
	minUnits = minUnits or 1
	
	local units = self:SecondsToTable(seconds)
	local result, skipping = "", true
	local unitsShown = 0

	local nonZeroUnits = 0
	for _, unit in ipairs(units) do
		if unit.Value then
			nonZeroUnits = #units - (_ - 1)
			break
		end
	end

	local startIndex = math.max(1, #units - minUnits + 1)
	for i, unit in ipairs(units) do
		if i < startIndex and not unit.Value and skipping then
			continue
		end

		skipping = false
		unitsShown = unitsShown + 1

		local previous = units[i - 1]
		local formatString = (unit.Overwrite or (previous and previous.Value) or false or unitsShown > 1) and ("%%0%dd"):format(unit.Occupies) or "%d"
		result = (i == #units and "%s%s" or "%s%s:"):format(result, formatString:format(unit.Value or 0))
	end

	return result
end

return m
