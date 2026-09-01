local Handler = {}

function Lerp(a, b, t)
	return a + (b - a) * t
end

function Handler.Quad(p0, p1, p2, t)
	local l1 = Lerp(p0, p1, t)
	local l2 = Lerp(p1, p2, t)

	return Lerp(l1, l2, t)
end

return Handler