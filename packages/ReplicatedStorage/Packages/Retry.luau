local MAX_RETRY_LENGTH = 120

local Rand = Random.new()

return function(maxRetries, initialDelay, f, ...)
	local result = { false }
	local current = initialDelay or 1

	for attempt = 1, maxRetries do
		result = { pcall(f, ...) }
		if result[1] then
			break
		end

		task.wait(current + (current * 0.1 * Rand:NextNumber(0, 1)))
		current = math.min(current * 1.5, MAX_RETRY_LENGTH)
	end

	return table.unpack(result)
end
