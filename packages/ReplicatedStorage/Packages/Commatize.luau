return function(n)
	n = tostring(tonumber(n) or 0)
	
	local substitutions
	repeat
		n, substitutions = n:gsub("^(-?%d+)(%d%d%d)", "%1,%2")
	until substitutions == 0
	
	return n
end