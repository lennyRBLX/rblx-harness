local IRREGULARS = {
	["child"] = "children",
	["foot"] = "feet",
	["tooth"] = "teeth",
	["man"] = "men",
	["woman"] = "women",
	["mouse"] = "mice",
	["goose"] = "geese",
	["ox"] = "oxen",
	["person"] = "people",
	["die"] = "dice",
	["fish"] = "fish",
	["sheep"] = "sheep",
	["deer"] = "deer",
	["moose"] = "moose",
	["species"] = "species",
	["series"] = "series"
}

local O_WORDS = {
	["hero"] = true, ["potato"] = true, ["tomato"] = true,
	["echo"] = true, ["torpedo"] = true, ["embargo"] = true,
	["cargo"] = true, ["mango"] = true, ["volcano"] = true
}

local ON_TO_A_WORDS = {
	["criterion"] = true,
	["phenomenon"] = true,
	["automaton"] = true,
	["polyhedron"] = true,

	["tetrahedron"] = true,
	["octahedron"] = true,
	["dodecahedron"] = true,
	["icosahedron"] = true,
	["hexahedron"] = true,
	["pentahedron"] = true,

	["protozoon"] = true,
	["spermatozoon"] = true,
	["ganglion"] = true,
	["mitochondrion"] = true,

	["asyndeton"] = true,
	["hyperbaton"] = true,
	["organan"] = true,
	["paradeigma"] = true
}

return function(word)
	if not word or word == "" then
		return word
	end

	local lowerWord = word:lower()
	local lastChar = lowerWord:sub(-1)
	local lastTwoChars = lowerWord:sub(-2)
	local lastThreeChars = lowerWord:sub(-3)

	if word:match("[%-']") then
		return word .. "'s"
	end

	if IRREGULARS[lowerWord] then
		local plural = IRREGULARS[lowerWord]
		if word:sub(1,1):match("%u") then
			plural = plural:sub(1,1):upper() .. plural:sub(2)
		end
		
		return plural
	end

	if lastChar == "y" and lastTwoChars:sub(1,1):match("[^aeiou]") then
		return word:sub(1, -2) .. "ies"
	end

	if lastChar == "f" then
		return word:sub(1, -2) .. "ves"
	elseif lastTwoChars == "fe" then
		return word:sub(1, -3) .. "ves"
	end

	if lastChar == "o" and #word > 1 then
		local beforeO = word:sub(-2, -2):lower()
		if beforeO:match("[^aeiou]") then
			return O_WORDS[lowerWord] and word .. "es" or word .. "s"
		end
	end

	if lastChar == "s" or lastChar == "x" or lastChar == "z" or 
		lastTwoChars == "sh" or lastTwoChars == "ch" or lastTwoChars == "ss" then
		return word .. "es"
	end

	if lastTwoChars == "is" then
		return word:sub(1, -3) .. "es"
	end

	if lastTwoChars == "us" then
		return word:sub(1, -3) .. "i"
	end

	if lastTwoChars == "um" then
		return word:sub(1, -3) .. "a"
	end

	if lastTwoChars == "on" and ON_TO_A_WORDS[lowerWord] then
		return word:sub(1, -2) .. "a"
	end

	return word .. "s"
end