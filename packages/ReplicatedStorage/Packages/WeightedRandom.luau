local Rand = Random.new()

return {
	Dictionary = function(self, list, r: Random?)
		local total = 0
		for _, weight in pairs(list) do
			total += weight
		end

		local value = (r or Rand):NextNumber(0, total)
		local cumulative = 0
		
		for key, weight in pairs(list) do
			cumulative += weight
			
			if value <= cumulative then
				return key
			end
		end

		return nil
	end,

	Array = function(self, list, r: Random?)
		local total = 0
		for _, item in ipairs(list) do
			total += item.Chance
		end

		local value = (r or Rand):NextNumber(0, total)
		local cumulative = 0
		
		for index, item in ipairs(list) do
			cumulative += item.Chance
			
			if value <= cumulative then
				return item, index
			end
		end

		return nil, nil
	end
}