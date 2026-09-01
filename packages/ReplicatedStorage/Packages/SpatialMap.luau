local m = {}
m.__index = m

-- privates
function m:normalize(position: Vector2 | Vector3)
	if typeof(position) ~= self.Mode then
		return
	end

	local result, scale = nil, self.Scale
	if self.Mode == "Vector2" then
		result = Vector2.new(
			math.floor(position.X / scale + 0.5) * scale,
			math.floor(position.Y / scale + 0.5) * scale
		)
	elseif self.Mode == "Vector3" then
		result = Vector3.new(
			math.floor(position.X / scale + 0.5) * scale,
			math.floor(position.Y / scale + 0.5) * scale,
			math.floor(position.Z / scale + 0.5) * scale
		)
	end

	return result
end

function m:nodeFor(position: Vector2 | Vector3)
	position = self:normalize(position)

	local nodes = self.Nodes
	local x, y = position.X, position.Y

	if self.Mode == "Vector2" then
		if not nodes[x] then
			nodes[x] = {}
		end

		if not nodes[x][y] then
			nodes[x][y] = {}
		end

		return nodes[x][y]
	elseif self.Mode == "Vector3" then
		if not nodes[x] then
			nodes[x] = {}
		end

		if not nodes[x][y] then
			nodes[x][y] = {}
		end

		if not nodes[x][y][position.Z] then
			nodes[x][y][position.Z] = {}
		end

		return nodes[x][y][position.Z]
	end
end

function m:neighbors(position: Vector2 | Vector3, range: number)
	position = self:normalize(position)

	local scale, nodes = self.Scale, self.Nodes
	local result = {}

	local half = math.floor(range / scale + 0.5) * scale * scale
	local x, y = position.X, position.Y

	if self.Mode == "Vector2" then
		for xx = x - half, x + half, scale do
			local column = nodes[xx]
			if not column then
				continue
			end

			for yy = y - half, y + half, scale do
				local row = column[yy]
				if not row then
					continue
				end

				for _, item in row do
					table.insert(result, item)
				end
			end
		end
	elseif self.Mode == "Vector3" then
		for xx = x - half, x + half, scale do
			local column = nodes[xx]
			if not column then
				continue
			end

			for yy = y - half, y + half, scale do
				local row = column[yy]
				if not row then
					continue
				end

				for zz = position.Z - half, position.Z + half, scale do
					local cell = row[zz]
					if not cell then
						continue
					end

					for _, item in cell do
						table.insert(result, item)
					end
				end
			end
		end
	end

	return result
end

function m:first(position: Vector2 | Vector3, range: number)
	position = self:normalize(position)

	local scale, nodes = self.Scale, self.Nodes
	local result = nil

	local half = math.floor(range / scale + 0.5) * scale * scale
	local x, y = position.X, position.Y

	if self.Mode == "Vector2" then
		for xx = x - half, x + half, scale do
			local column = nodes[xx]
			if not column then
				continue
			end

			for yy = y - half, y + half, scale do
				local row = column[yy]
				if row then
					local _, r = next(row)
					result = r
					break
				end
			end

			if result then
				break
			end
		end
	elseif self.Mode == "Vector3" then
		for xx = x - half, x + half, scale do
			local column = nodes[xx]
			if not column then
				continue
			end

			for yy = y - half, y + half, scale do
				local row = column[yy]
				if not row then
					continue
				end

				for zz = position.Z - half, position.Z + half, scale do
					local cell = row[zz]
					if cell then
						local _, r = next(cell)
						result = r
						break
					end
				end

				if result then
					break
				end
			end

			if result then
				break
			end
		end
	end

	return result
end

function m:deleteIn(position: Vector2 | Vector3, range: number)
	position = self:normalize(position)

	local scale, nodes = self.Scale, self.Nodes
	local half = math.floor(range / scale + 0.5) * scale * scale
	local x, y = position.X, position.Y

	if self.Mode == "Vector2" then
		for xx = x - half, x + half, scale do
			local column = nodes[xx]
			if not column then
				continue
			end

			for yy = y - half, y + half, scale do
				local row = column[yy]
				if row then
					table.clear(row)
				end
			end
		end
	elseif self.Mode == "Vector3" then
		for xx = x - half, x + half, scale do
			local column = nodes[xx]
			if not column then
				continue
			end

			for yy = y - half, y + half, scale do
				local row = column[yy]
				if not row then
					continue
				end

				for zz = position.Z - half, position.Z + half, scale do
					local cell = row[zz]
					if cell then
						table.clear(cell)
					end
				end
			end
		end
	end
end

function m:delete(position: Vector2 | Vector3, hashed: number)
	local node = self:nodeFor(position)
	if not node then
		return
	end

	local index = table.find(node, hashed)
	if index then
		table.remove(node, index)
	end
end

-- functions
function m.new(mode: "Vector2" | "Vector3" | nil, scale: number)
	local self = setmetatable({}, m)
	self.Mode = mode or "Vector3"
	self.Scale = tonumber(scale) or 1
	self.Nodes = {}

	return self
end

function m:Add(position: Vector2 | Vector3, hashed: number)
	local node = self:nodeFor(position)
	if node then
		table.insert(node, hashed)
	end
end

function m:Remove(position: Vector2 | Vector3, idOrRange: number, asAround: boolean?)
	return (asAround and self:deleteIn(position, idOrRange)) or self:delete(position, idOrRange)
end

function m:Get(position: Vector2 | Vector3, range: number, withNeighbors: boolean?)
	return (withNeighbors and self:neighbors(position, range)) or self:first(position, range)
end

return m