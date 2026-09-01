--[[
AStar:
	Grid-based A* pathfinding on the X,Z plane. Builds a 2D walkability
	grid from floor and wall BasePart geometry, then finds shortest paths
	between world positions returning ordered Vector3 waypoints.

	Adapted from the RapidFire Studio A* implementation (astar.lua),
	restructured for grid-based 2D navigation in Luau.

	Usage:
		local AStar = require(ReplicatedStorage.Packages.AStar)
		local grid = AStar.new({
			Floors = floorParts,
			Walls  = wallParts,
			GridSize = 40,
		})
		local waypoints = grid:FindPath(startPos, goalPos)
]]

local CollectionService = game:GetService("CollectionService")

local INF = 1 / 0
local CARDINAL = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }
local DEFAULT_GRID_SIZE = 40
local SNAP_RADIUS = 3
local WAYPOINT_Y_OFFSET = 3

type Cell = {
	GX: number,
	GZ: number,
	WorldY: number,
	Walkable: boolean,
	Cost: number?,
	Section: string?,
	SectionId: string?,
}

type Config = {
	Floors: { BasePart },
	WalkHeight: number?,
	GridSize: number?,
}

local AStar = {}
AStar.__index = AStar

-- privates
local function gk(gx: number, gz: number): string
	return string.format("%d_%d", gx, gz)
end

local function heuristic(a: Cell, b: Cell): number
	return math.abs(a.GX - b.GX) + math.abs(a.GZ - b.GZ)
end

local function lowestFScore(openSet: { Cell }, fScore: { [string]: number }): (Cell, number)
	local lowest, bestNode, bestIndex = INF, nil, 0
	for i, node in openSet do
		local key = gk(node.GX, node.GZ)
		local score = fScore[key] or INF
		if score < lowest then
			lowest = score
			bestNode = node
			bestIndex = i
		end
	end
	return bestNode, bestIndex
end

local function removeNode(set: { Cell }, index: number)
	local n = #set
	set[index] = set[n]
	set[n] = nil
end

local function unwindPath(cameFrom: { [string]: Cell }, current: Cell): { Cell }
	local path = { current }
	local key = gk(current.GX, current.GZ)
	while cameFrom[key] do
		current = cameFrom[key]
		key = gk(current.GX, current.GZ)
		table.insert(path, 1, current)
	end
	return path
end

function AStar:buildGrid(floors: { BasePart })
	local cells: { [string]: Cell } = {}
	local gridSize = self.__gridSize
	local PROBE_HEIGHT = 8

	local floorSet = {}
	for _, part in floors do
		floorSet[part] = true
	end

	if #floors == 0 then
		warn("[AStar:buildGrid] NO FLOORS — grid empty")
		self.__cells = cells
		return
	end

	warn(string.format("[AStar:buildGrid] START — %d floor parts, gridSize=%d", #floors, gridSize))

	-- Step 1: generate cells per carpet part in object space
	-- Uses CFrame:PointToWorldSpace to handle rotated parts correctly.
	-- Grid keys use math.floor for collision-free mapping.
	local totalCreated = 0

	for fi, part in floors do
		local size = part.Size
		local cf = part.CFrame

		local cols = math.ceil(size.X / gridSize)
		local rows = math.ceil(size.Z / gridSize)

		if cols == 0 or rows == 0 then continue end

		-- trace section for debug linking
		local sectionModel = part.Parent
		while sectionModel and sectionModel.Parent and sectionModel.Parent.Name ~= "Floor0" and not sectionModel.Parent:IsA("Workspace") do
			sectionModel = sectionModel.Parent
		end
		local sectionName = sectionModel and sectionModel.Name or "?"
		local sectionId = sectionModel and sectionModel:GetAttribute("ID") or nil

		local originX = -size.X / 2 + gridSize / 2
		local originZ = -size.Z / 2 + gridSize / 2
		local topY = size.Y / 2

		local partCreated = 0
		for r = 0, rows - 1 do
			for c = 0, cols - 1 do
				local localPos = Vector3.new(
					originX + c * gridSize,
					topY,
					originZ + r * gridSize
				)
				local worldPos = cf:PointToWorldSpace(localPos)

				local gx = math.floor(worldPos.X / gridSize)
				local gz = math.floor(worldPos.Z / gridSize)
				local key = gk(gx, gz)

				local existing = cells[key]
				if not existing or worldPos.Y < existing.WorldY then
					cells[key] = {
						GX = gx,
						GZ = gz,
						WorldY = worldPos.Y,
						Walkable = true,
						Section = sectionName,
						SectionId = sectionId,
					}
					if not existing then
						partCreated += 1
					end
				end
			end
		end

		totalCreated += partCreated
		local parentName = part.Parent and part.Parent.Name or "?"
		local grandparent = part.Parent and part.Parent.Parent and part.Parent.Parent.Name or "?"

		warn(string.format("[AStar:buildGrid]   floor[%d] '%s' in %s/%s pos=%.0f,%.0f,%.0f sz=%.1f,%.1f,%.1f rot=%s → %dx%d=%d cells (%d new)",
			fi, part.Name, grandparent, parentName,
			part.Position.X, part.Position.Y, part.Position.Z,
			size.X, size.Y, size.Z,
			cf.Rotation ~= CFrame.identity.Rotation and "YES" or "no",
			cols, rows, cols * rows, partCreated))
	end

	warn(string.format("[AStar:buildGrid] Step 1 done — %d unique cells from %d floors", totalCreated, #floors))

	-- Step 2: walkability check via GetPartsInPart
	-- Uses actual geometry (not bounding boxes) so hollow Unions don't false-block.
	-- Create a reusable probe Part for GetPartsInPart.
	local queryParams = OverlapParams.new()
	queryParams.FilterType = Enum.RaycastFilterType.Exclude
	queryParams.FilterDescendantsInstances = floors

	local probeSize = Vector3.new(gridSize, PROBE_HEIGHT, gridSize)
	local probePart = Instance.new("Part")
	probePart.Size = probeSize
	probePart.Anchored = true
	probePart.CanCollide = false
	probePart.CanQuery = false
	probePart.Transparency = 1
	probePart.Parent = workspace.Terrain

	local blockedCount = 0

	warn(string.format("[AStar:buildGrid] Step 2 — probing %d cells with GetPartsInPart, probeSize=%s", totalCreated, tostring(probeSize)))

	for _, cell in cells do
		if not cell.Walkable then
			continue
		end

		probePart.CFrame = CFrame.new(
			(cell.GX + 0.5) * gridSize,
			cell.WorldY + PROBE_HEIGHT / 2,
			(cell.GZ + 0.5) * gridSize
		)

		local hits = workspace:GetPartsInPart(probePart, queryParams)

		for _, hit in hits do
			if floorSet[hit] then continue end
			if hit.Transparency >= 1 or not hit.CanCollide then continue end

			if hit.Material == Enum.Material.Fabric or CollectionService:HasTag(hit, "Prop") then
				cell.Walkable = false
				blockedCount += 1
				break
			end
		end
	end

	probePart:Destroy()

	warn(string.format("[AStar:buildGrid] Step 2 done — %d cells blocked", blockedCount))

	-- Step 3: prune isolated cells (no walkable cardinal neighbor)
	local prunedCount = 0
	for _, cell in cells do
		if not cell.Walkable then
			continue
		end

		local hasNeighbor = false
		for _, dir in CARDINAL do
			local nk = gk(cell.GX + dir[1], cell.GZ + dir[2])
			local neighbor = cells[nk]
			if neighbor and neighbor.Walkable then
				hasNeighbor = true
				break
			end
		end

		if not hasNeighbor then
			cell.Walkable = false
			prunedCount += 1
		end
	end

	local finalWalkable, finalBlocked = 0, 0
	for _, cell in cells do
		if cell.Walkable then finalWalkable += 1 else finalBlocked += 1 end
	end

	warn(string.format("[AStar:buildGrid] Step 3 done — %d pruned. FINAL: %d total (%d walkable, %d blocked)",
		prunedCount, finalWalkable + finalBlocked, finalWalkable, finalBlocked))

	self.__cells = cells
end

function AStar:worldToGrid(pos: Vector3): (number, number)
	return math.floor(pos.X / self.__gridSize), math.floor(pos.Z / self.__gridSize)
end

function AStar:gridToWorld(cell: Cell): Vector3
	return Vector3.new(
		(cell.GX + 0.5) * self.__gridSize,
		cell.WorldY + WAYPOINT_Y_OFFSET,
		(cell.GZ + 0.5) * self.__gridSize
	)
end

function AStar:snapToWalkable(pos: Vector3): Cell?
	local gx, gz = self:worldToGrid(pos)
	local key = gk(gx, gz)
	local cell = self.__cells[key]
	if cell and cell.Walkable then
		return cell
	end

	for radius = 1, SNAP_RADIUS do
		for dx = -radius, radius do
			for dz = -radius, radius do
				if math.abs(dx) == radius or math.abs(dz) == radius then
					local nk = gk(gx + dx, gz + dz)
					local neighbor = self.__cells[nk]
					if neighbor and neighbor.Walkable then
						return neighbor
					end
				end
			end
		end
	end

	return nil
end

function AStar:simplifyPath(path: { Vector3 }): { Vector3 }
	if #path <= 2 then
		return path
	end

	local result = { path[1] }
	for i = 2, #path - 1 do
		local prev = path[i - 1]
		local curr = path[i]
		local next = path[i + 1]

		local dx1 = curr.X - prev.X
		local dz1 = curr.Z - prev.Z
		local dx2 = next.X - curr.X
		local dz2 = next.Z - curr.Z

		if not (dx1 == dx2 and dz1 == dz2) then
			table.insert(result, curr)
		end
	end
	table.insert(result, path[#path])

	return result
end

-- functions
function AStar.new(config: Config)
	local self = setmetatable({}, AStar)
	self.__gridSize = config.GridSize or DEFAULT_GRID_SIZE
	self.__cells = {}

	self.__walkHeight = config.WalkHeight or 6
	self:buildGrid(config.Floors)
	return self
end

function AStar.newFromCells(cells: { [string]: Cell }, gridSize: number)
	local self = setmetatable({}, AStar)
	self.__gridSize = gridSize
	self.__cells = cells
	self.__walkHeight = 6
	return self
end

function AStar:FindPath(startPos: Vector3, goalPos: Vector3): { Vector3 }?
	local startCell = self:snapToWalkable(startPos)
	local goalCell = self:snapToWalkable(goalPos)
	if not startCell or not goalCell then
		return nil
	end

	local startKey = gk(startCell.GX, startCell.GZ)
	local goalKey = gk(goalCell.GX, goalCell.GZ)

	if startKey == goalKey then
		return { self:gridToWorld(goalCell) }
	end

	local openSet: { Cell } = { startCell }
	local openSetKeys: { [string]: boolean } = { [startKey] = true }
	local closedSet: { [string]: boolean } = {}
	local cameFrom: { [string]: Cell } = {}
	local gScore: { [string]: number } = { [startKey] = 0 }
	local fScore: { [string]: number } = { [startKey] = heuristic(startCell, goalCell) }

	while #openSet > 0 do
		local current, currentIndex = lowestFScore(openSet, fScore)
		local currentKey = gk(current.GX, current.GZ)

		if currentKey == goalKey then
			local cellPath = unwindPath(cameFrom, current)
			local worldPath = {}
			for _, cell in cellPath do
				table.insert(worldPath, self:gridToWorld(cell))
			end
			return self:simplifyPath(worldPath)
		end

		removeNode(openSet, currentIndex)
		openSetKeys[currentKey] = nil
		closedSet[currentKey] = true

		for _, dir in CARDINAL do
			local nx, nz = current.GX + dir[1], current.GZ + dir[2]
			local neighborKey = gk(nx, nz)
			local neighbor = self.__cells[neighborKey]

			if not neighbor or not neighbor.Walkable or closedSet[neighborKey] then
				continue
			end

			local tentativeG = (gScore[currentKey] or INF) + (neighbor.Cost or 1)

			if tentativeG < (gScore[neighborKey] or INF) then
				cameFrom[neighborKey] = current
				gScore[neighborKey] = tentativeG
				fScore[neighborKey] = tentativeG + heuristic(neighbor, goalCell)

				if not openSetKeys[neighborKey] then
					table.insert(openSet, neighbor)
					openSetKeys[neighborKey] = true
				end
			end
		end
	end

	return nil
end

function AStar:IsWalkable(worldPos: Vector3): boolean
	local gx, gz = self:worldToGrid(worldPos)
	local cell = self.__cells[gk(gx, gz)]
	return cell ~= nil and cell.Walkable
end

function AStar:GetCellCenter(worldPos: Vector3): Vector3?
	local gx, gz = self:worldToGrid(worldPos)
	local cell = self.__cells[gk(gx, gz)]
	if not cell then
		return nil
	end
	return self:gridToWorld(cell)
end

function AStar:GetAllCells(): { Cell }
	local result = {}
	for _, cell in self.__cells do
		table.insert(result, cell)
	end
	return result
end

function AStar:GetCellsTable()
	return self.__cells
end

function AStar:GetGridSize(): number
	return self.__gridSize
end

function AStar:Rebuild(floors: { BasePart })
	self:buildGrid(floors)
end

function AStar:Destroy()
	table.clear(self.__cells)
	setmetatable(self, nil)
end

return AStar
