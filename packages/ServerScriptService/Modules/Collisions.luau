-- Finite box queries for Workspace Block Parts; use dot calls from serial server code.
-- One module-owned registry: Register/Unregister manage exclusive Static/Dynamic
-- membership, SetMotion transfers it, and Refresh updates a retained static snapshot.
-- Configure is optional (StaticGridThreshold defaults to 1024). Clear releases all
-- registrations/connections, retains configuration, and leaves the module usable.
-- StaticGetPartsIn and DynamicGetPartsIn return fresh, unordered, unique Part arrays.
-- Partial overlap counts, including Parts with centers outside the query box.
-- Before moving a static fragment, SetMotion(part, "Dynamic"). After changing a
-- retained static Part's CFrame, Size, Shape, CanQuery, or CollisionGroup, call
-- Refresh(part) before querying. Property signals are a safety measure only.
-- Parts leaving Workspace require Register again before reuse.
--
-- Static count > threshold selects private GridSAT for supported profiles. This
-- O(1) count covers the whole static registry before arbitrary descendant filters.
-- Dynamic queries and unsupported static profiles use GetPartBoundsInBox.
-- Grid: 16-stud cells, 15-axis SAT, tolerance 1e-7; finite policy budgets are
-- 512 memberships/Part, 262144 total memberships, and 4096 cells/query.
-- Excess memberships use a separate SAT list; excess query cells use BoxBounds.
-- Grid requires MaxParts=0, Tolerance=0, RespectCanCollide=false,
-- BruteForceAllSlow=false, CanQuery=true, Default query/Part groups, and a
-- successful current Default/Default matrix read. Other profiles use BoxBounds.
-- Simple Include/Exclude filters share exact-instance-or-descendant checks.
-- Mixed modern lists or active legacy+modern filters use an unlimited engine
-- filter query, intersected with registered hits, to preserve engine semantics.
-- Caller filter entries are copied per call. Positive MaxParts applies afterward.
--
-- Inert usage (the caller supplies existing Workspace Block Parts):
-- const Collisions = require(game:GetService("ServerScriptService").Modules.Collisions)
-- Collisions.Configure({ StaticGridThreshold = 1024 }) -- optional
-- Collisions.Register(buildingPart, "Static")
-- Collisions.Register(limbPart, "Dynamic")
-- const buildings = Collisions.StaticGetPartsIn(queryCFrame, querySize, overlapParams)
-- const limbs = Collisions.DynamicGetPartsIn(queryCFrame, querySize, overlapParams)
-- Collisions.SetMotion(buildingPart, "Dynamic") -- before moving the fragment
-- Collisions.Refresh(retainedStaticPart) -- after changing its geometry/query flags
-- Collisions.Unregister(limbPart)
-- Collisions.Clear()
--
-- Runtime correctness/performance, all-Part and combined-query costs, destruction
-- churn, memory/GC, and frame intervals are unrun. Threshold/budgets are unmeasured
-- policies. Exact tangency equivalence remains unresolved.
-- Engine evidence: Creator Docs 031b2f91d3d47274c255f3ed5691c29f792c181d;
-- API dump 890b70c4a8c7b7ef739117e017742e49699b1a18d958c314fae729b1324a9997.
-- Docs' general exclude priority conflicts with Physics Team's nested-list rules:
-- https://devforum.roblox.com/t/new-spatial-query-filters/4563575
-- https://create.roblox.com/docs/reference/engine/datatypes/OverlapParams

export type Motion = "Static" | "Dynamic"

export type Config = {
	StaticGridThreshold: number?, -- default 1024; GridSAT when count > threshold
}

export type API = {
	Configure: (config: Config) -> (),
	Register: (part: Part, motion: Motion) -> (),
	Unregister: (part: Part) -> (),
	SetMotion: (part: Part, motion: Motion) -> (),
	Refresh: (part: Part) -> (),
	StaticGetPartsIn: (
		cframe: CFrame, size: Vector3, overlapParams: OverlapParams?
	) -> {Part},
	DynamicGetPartsIn: (
		cframe: CFrame, size: Vector3, overlapParams: OverlapParams?
	) -> {Part},
	Clear: () -> (),
}

type ResolvedConfig = { read StaticGridThreshold: number }
type Box = {
	center: Vector3,
	half: Vector3,
	axes: {Vector3},
	minimum: Vector3,
	maximum: Vector3,
}
type FilterSnapshot = {
	include: {Instance}?,
	exclude: {Instance}?,
	legacyEntries: {Instance},
	legacyType: Enum.RaycastFilterType,
	modernActive: boolean,
	engineFilterRequired: boolean,
	maxParts: number,
	tolerance: number,
	respectCanCollide: boolean,
	bruteForceAllSlow: boolean,
	collisionGroup: string,
}
type ConnectionOwnership = {RBXScriptConnection}
type Membership = { box: Box, keys: {string} }
type GridCell = {[Part]: boolean}
type GridState = {
	cells: {[string]: GridCell},
	rows: {[Part]: Membership},
	overflow: {[Part]: Box},
	membershipCount: number,
}
type CellRange = {
	minX: number, minY: number, minZ: number,
	maxX: number, maxY: number, maxZ: number,
}
type RegistryRecord = {
	part: Part,
	motion: Motion,
	gridSupported: boolean,
	connections: ConnectionOwnership,
	staticConnections: ConnectionOwnership,
}
type DirtyRecords = {[Part]: RegistryRecord}
type PartSet = { parts: {Part}, indices: {[Part]: number}, count: number }
type QueryScratch = { selected: {Instance}, visited: {[Part]: boolean} }
type RegistryState = {
	static: PartSet,
	dynamic: PartSet,
	records: {[Part]: RegistryRecord},
	dirty: DirtyRecords,
	grid: GridState,
	unsupportedStaticCount: number,
	scratch: QueryScratch,
}
type EngineFilterHits = {[BasePart]: boolean}
-- The scoped API dump includes this WorldRoot method; pinned globals omit it.
type CollisionMatrixReader = {
	CollisionGroupsAreCollidable: (self: CollisionMatrixReader, name1: string, name2: string) -> boolean,
}

const Workspace = game:GetService("Workspace")
const DEFAULT_STATIC_GRID_THRESHOLD = 1024
const CELL_SIZE = 16
const PART_MEMBERSHIP_BUDGET = 512
const TOTAL_MEMBERSHIP_BUDGET = 262144
const QUERY_CELL_BUDGET = 4096
const MAX_CELL_COORDINATE = 2 ^ 40
const ORTHONORMAL_TOLERANCE = 1e-5
const SAT_TOLERANCE = 1e-7
const STATIC_PROPERTIES: {string} = {"CFrame", "Size", "Shape", "CanQuery", "CollisionGroup"}
local configuration: ResolvedConfig = table.freeze({StaticGridThreshold = DEFAULT_STATIC_GRID_THRESHOLD})
const registry: RegistryState = {
	static = {parts = {}, indices = {}, count = 0},
	dynamic = {parts = {}, indices = {}, count = 0},
	records = {}, dirty = {}, unsupportedStaticCount = 0,
	grid = {cells = {}, rows = {}, overflow = {}, membershipCount = 0},
	scratch = {selected = {}, visited = {}},
}

const function finite(value: number): boolean
	return value == value and value > -math.huge and value < math.huge
end

const function validateBox(cframe: CFrame, size: Vector3): ()
	if typeof(cframe) ~= "CFrame" or typeof(size) ~= "Vector3" then
		error("Collisions: expected CFrame and Vector3", 2)
	end

	const components: {number} = {cframe:GetComponents()}
	for _, component in components do
		if not finite(component) then
			error("Collisions: CFrame components must be finite", 2)
		end
	end
	if not finite(size.X) or not finite(size.Y) or not finite(size.Z)
		or size.X <= 0 or size.Y <= 0 or size.Z <= 0 then
		error("Collisions: size components must be positive and finite", 2)
	end
end

const function resolveConfig(config: Config, current: ResolvedConfig): ResolvedConfig
	if typeof(config) ~= "table" then
		error("Collisions: config must be a table", 2)
	end

	const threshold = if config.StaticGridThreshold ~= nil
		then config.StaticGridThreshold else current.StaticGridThreshold
	if typeof(threshold) ~= "number" or not finite(threshold) or threshold < 0 or threshold % 1 ~= 0 then
		error("Collisions: StaticGridThreshold must be a finite nonnegative integer", 2)
	end

	return table.freeze({StaticGridThreshold = threshold})
end

const function validateMotion(motion: Motion): ()
	if motion ~= "Static" and motion ~= "Dynamic" then
		error('Collisions: motion must be "Static" or "Dynamic"', 2)
	end
end

const function validatePartInstance(part: Part): ()
	if typeof(part) ~= "Instance" or not part:IsA("Part") then
		error("Collisions: expected a rectangular Block Part", 2)
	end
end

const function copyInstances(entries: {Instance}?): {Instance}?
	if entries == nil then
		return nil
	end

	const copy: {Instance} = {}
	for _, entry in entries do
		if typeof(entry) ~= "Instance" then
			error("Collisions: filter entries must be Instances", 2)
		end
		table.insert(copy, entry)
	end

	return copy
end

const function snapshotFilter(params: OverlapParams?): FilterSnapshot
	if params == nil then
		return {
			include = nil, exclude = nil, legacyEntries = {},
			legacyType = Enum.RaycastFilterType.Exclude,
			modernActive = false, engineFilterRequired = false,
			maxParts = 0, tolerance = 0, respectCanCollide = false,
			bruteForceAllSlow = false, collisionGroup = "Default",
		}
	end
	if typeof(params) ~= "OverlapParams" then
		error("Collisions: expected OverlapParams", 2)
	end

	const legacyType = params.FilterType
	if legacyType ~= Enum.RaycastFilterType.Include and legacyType ~= Enum.RaycastFilterType.Exclude then
		error("Collisions: invalid filter enum", 2)
	end

	-- Current docs allow nil modern lists even though the pinned API types omit '?'.
	-- copyInstances accepts and preserves nil without changing the caller's object.
	const include = copyInstances(params.IncludeInstances)
	const exclude = copyInstances(params.ExcludeInstances)
	const legacyEntries: {Instance} = copyInstances(params.FilterDescendantsInstances) or {}
	const modernActive = include ~= nil or exclude ~= nil
	const legacyActive = legacyType == Enum.RaycastFilterType.Include or #legacyEntries > 0
	const mixedModern = include ~= nil and exclude ~= nil and #include > 0 and #exclude > 0
	const maxParts, tolerance = params.MaxParts, params.Tolerance
	if not finite(maxParts) or maxParts < 0 or maxParts % 1 ~= 0 then
		error("Collisions: MaxParts must be a finite nonnegative integer", 2)
	end
	if not finite(tolerance) or tolerance < 0 then
		error("Collisions: Tolerance must be finite and nonnegative", 2)
	end

	return {
		include = include, exclude = exclude,
		legacyEntries = legacyEntries, legacyType = legacyType,
		modernActive = modernActive,
		engineFilterRequired = mixedModern or (modernActive and legacyActive),
		maxParts = maxParts, tolerance = tolerance,
		respectCanCollide = params.RespectCanCollide,
		bruteForceAllSlow = params.BruteForceAllSlow,
		collisionGroup = params.CollisionGroup,
	}
end

const function matches(part: Part, entries: {Instance}): boolean
	for _, entry in entries do
		if part == entry or part:IsDescendantOf(entry) then
			return true
		end
	end

	return false
end

const function accepts(part: Part, filter: FilterSnapshot, engineHits: EngineFilterHits?): boolean
	if engineHits then
		return engineHits[part] == true
	end

	if filter.modernActive then
		const include, exclude = filter.include, filter.exclude
		return (include == nil or matches(part, include))
			and (exclude == nil or not matches(part, exclude))
	elseif filter.legacyType == Enum.RaycastFilterType.Include then
		return matches(part, filter.legacyEntries)
	end

	return not matches(part, filter.legacyEntries)
end

-- Full world AABB of an oriented box; never use just the Part's center.
const function snapshotBox(cframe: CFrame, size: Vector3): Box
	const half = size * 0.5
	const x, y, z = cframe.XVector, cframe.YVector, cframe.ZVector
	const extent = Vector3.new(
		math.abs(x.X) * half.X + math.abs(y.X) * half.Y + math.abs(z.X) * half.Z,
		math.abs(x.Y) * half.X + math.abs(y.Y) * half.Y + math.abs(z.Y) * half.Z,
		math.abs(x.Z) * half.X + math.abs(y.Z) * half.Y + math.abs(z.Z) * half.Z
	)

	return {
		center = cframe.Position, half = half, axes = {x, y, z},
		minimum = cframe.Position - extent, maximum = cframe.Position + extent,
	}
end

const function separates(a: Box, b: Box, delta: Vector3, axis: Vector3): boolean
	const aa, ba, ah, bh = a.axes, b.axes, a.half, b.half
	const distance = math.abs(delta:Dot(axis))
	const radiusA = ah.X * math.abs(aa[1]:Dot(axis))
		+ ah.Y * math.abs(aa[2]:Dot(axis)) + ah.Z * math.abs(aa[3]:Dot(axis))
	const radiusB = bh.X * math.abs(ba[1]:Dot(axis))
		+ bh.Y * math.abs(ba[2]:Dot(axis)) + bh.Z * math.abs(ba[3]:Dot(axis))

	return distance > radiusA + radiusB + SAT_TOLERANCE
end

const function overlaps(a: Box, b: Box): boolean
	const delta, aa, ba = b.center - a.center, a.axes, b.axes
	for i = 1, 3 do
		if separates(a, b, delta, aa[i]) or separates(a, b, delta, ba[i]) then
			return false
		end
	end
	for i = 1, 3 do
		for j = 1, 3 do
			if separates(a, b, delta, aa[i]:Cross(ba[j])) then
				return false
			end
		end
	end

	return true
end

const function gridSupports(box: Box): boolean
	-- Finite public components can overflow derived Vector3 math. Raw CFrame
	-- matrices need not be orthonormal. Both cases use the engine instead.
	for _, point in {box.minimum, box.maximum} do
		for _, value in {point.X, point.Y, point.Z} do
			if not finite(value) or math.abs(value) > MAX_CELL_COORDINATE * CELL_SIZE then
				return false
			end
		end
	end
	for i = 1, 3 do
		if math.abs(box.axes[i]:Dot(box.axes[i]) - 1) > ORTHONORMAL_TOLERANCE then
			return false
		end
		for j = i + 1, 3 do
			if math.abs(box.axes[i]:Dot(box.axes[j])) > ORTHONORMAL_TOLERANCE then
				return false
			end
		end
	end

	return true
end

const function cellKey(x: number, y: number, z: number): string
	return string.format("%.0f:%.0f:%.0f", if x == 0 then 0 else x, if y == 0 then 0 else y, if z == 0 then 0 else z)
end

const function cellRange(box: Box, budget: number): CellRange?
	-- Scalar division avoids an extra float32 Vector3 rounding at cell boundaries.
	const minX = math.floor(box.minimum.X / CELL_SIZE)
	const minY = math.floor(box.minimum.Y / CELL_SIZE)
	const minZ = math.floor(box.minimum.Z / CELL_SIZE)
	const maxX = math.floor(box.maximum.X / CELL_SIZE)
	const maxY = math.floor(box.maximum.Y / CELL_SIZE)
	const maxZ = math.floor(box.maximum.Z / CELL_SIZE)
	const count = (maxX - minX + 1) * (maxY - minY + 1) * (maxZ - minZ + 1)
	if not finite(count) or count > budget or count <= 0 then
		return nil
	end

	return {minX = minX, minY = minY, minZ = minZ, maxX = maxX, maxY = maxY, maxZ = maxZ}
end

const function removeGrid(grid: GridState, part: Part): ()
	const row = grid.rows[part]
	if not row then
		return
	end

	for _, id in row.keys do
		const cell = grid.cells[id]
		cell[part] = nil
		if next(cell) == nil then
			grid.cells[id] = nil
		end
	end
	grid.membershipCount -= #row.keys
	grid.overflow[part] = nil
	grid.rows[part] = nil
end

const function putGrid(grid: GridState, part: Part, box: Box): ()
	removeGrid(grid, part)
	const bounds = if gridSupports(box)
		then cellRange(box, math.min(PART_MEMBERSHIP_BUDGET, TOTAL_MEMBERSHIP_BUDGET - grid.membershipCount))
		else nil
	const keys: {string} = {}
	grid.rows[part] = {box = box, keys = keys}
	if not bounds then
		grid.overflow[part] = box
		return
	end

	for x = bounds.minX, bounds.maxX do
		for y = bounds.minY, bounds.maxY do
			for z = bounds.minZ, bounds.maxZ do
				const id = cellKey(x, y, z)
				local cell = grid.cells[id]
				if not cell then
					cell = {}
					grid.cells[id] = cell
				end
				cell[part] = true
				table.insert(keys, id)
			end
		end
	end
	grid.membershipCount += #keys
end

const function collectGrid(grid: GridState, scratch: QueryScratch, query: Box, eligible: (Part) -> boolean): {Part}?
	if not gridSupports(query) then
		return nil
	end

	const bounds = cellRange(query, QUERY_CELL_BUDGET)
	if not bounds then
		return nil
	end

	const visited = scratch.visited
	const hits: {Part} = {}
	const function collect(part: Part, box: Box): ()
		if visited[part] then
			return
		end

		visited[part] = true
		if eligible(part) and overlaps(query, box) then
			table.insert(hits, part)
		end
	end

	for x = bounds.minX, bounds.maxX do
		for y = bounds.minY, bounds.maxY do
			for z = bounds.minZ, bounds.maxZ do
				const cell = grid.cells[cellKey(x, y, z)]
				if cell then
					for part in cell do
						const row = grid.rows[part]
						if row then
							collect(part, row.box)
						end
					end
				end
			end
		end
	end
	for part, box in grid.overflow do
		collect(part, box)
	end

	return hits
end

const function clearGrid(grid: GridState): ()
	table.clear(grid.cells)
	table.clear(grid.rows)
	table.clear(grid.overflow)
	grid.membershipCount = 0
end

const function disconnect(connections: ConnectionOwnership): ()
	for _, connection in connections do
		connection:Disconnect()
	end
	table.clear(connections)
end

const function addPart(set: PartSet, part: Part): ()
	set.count += 1
	set.parts[set.count] = part
	set.indices[part] = set.count
end

const function removePart(set: PartSet, part: Part): ()
	const index = set.indices[part]
	if not index then
		return
	end

	const last = set.parts[set.count]
	set.parts[index] = last
	set.indices[last] = index
	set.parts[set.count] = nil
	set.indices[part] = nil
	set.count -= 1
end

const function removeStatic(state: RegistryState, record: RegistryRecord): ()
	removeGrid(state.grid, record.part)
	state.dirty[record.part] = nil
	if not record.gridSupported then
		state.unsupportedStaticCount -= 1
	end
	disconnect(record.staticConnections)
end

const function unregister(state: RegistryState, part: Part): ()
	const record = state.records[part]
	if not record then
		return
	end

	state.records[part] = nil
	if record.motion == "Static" then
		removeStatic(state, record)
		removePart(state.static, part)
	else
		removePart(state.dynamic, part)
	end
	disconnect(record.connections)
end

const function validateRetained(state: RegistryState, part: Part): ()
	validatePartInstance(part)
	if part.Shape ~= Enum.PartType.Block then
		if state.records[part] then
			unregister(state, part)
		end
		error("Collisions: expected Block Part; any existing registration was removed", 2)
	end
	if not part:IsDescendantOf(Workspace) then
		if state.records[part] then
			unregister(state, part)
		end
		error("Collisions: Part must be a Workspace descendant; register again after removal", 2)
	end

	validateBox(part.CFrame, part.Size)
end

const function storeStatic(state: RegistryState, record: RegistryRecord, box: Box): ()
	-- False CanQuery with true CanCollide has qualified engine semantics.
	-- Keep all false CanQuery profiles on BoxBounds rather than guessing.
	record.gridSupported = record.part.CanQuery and record.part.CollisionGroup == "Default" and gridSupports(box)
	if not record.gridSupported then
		state.unsupportedStaticCount += 1
	end
	putGrid(state.grid, record.part, box)
	for _, property in STATIC_PROPERTIES do
		table.insert(record.staticConnections, record.part:GetPropertyChangedSignal(property):Connect(function(): ()
			if state.records[record.part] == record and record.motion == "Static" then
				state.dirty[record.part] = record
			end
		end))
	end
end

const function connectLifecycle(state: RegistryState, record: RegistryRecord): ()
	const part = record.part
	table.insert(record.connections, part.Destroying:Connect(function(): ()
		if state.records[part] == record then
			unregister(state, part)
		end
	end))
	-- DescendantRemoving reports the Part even when an ancestor leaves Workspace.
	-- Capture record ownership: an old queued callback cannot remove a replacement
	-- registration after the caller explicitly registers the returned Part again.
	table.insert(record.connections, Workspace.DescendantRemoving:Connect(function(descendant: Instance): ()
		if descendant == part and state.records[part] == record then
			unregister(state, part)
		end
	end))
end

const function register(state: RegistryState, part: Part, motion: Motion): ()
	validateMotion(motion)
	validateRetained(state, part)
	const box = if motion == "Static" then snapshotBox(part.CFrame, part.Size) else nil
	-- Replacement keeps one registration and snapshot, and retires old callbacks.
	unregister(state, part)
	const record: RegistryRecord = {
		part = part, motion = motion, gridSupported = false,
		connections = {}, staticConnections = {},
	}
	state.records[part] = record
	addPart(if motion == "Static" then state.static else state.dynamic, part)
	connectLifecycle(state, record)
	if box then
		storeStatic(state, record, box)
	end
end

const function setMotion(state: RegistryState, part: Part, motion: Motion): ()
	validateMotion(motion)
	validatePartInstance(part)
	if not state.records[part] then
		error("Collisions: SetMotion requires registration", 2)
	end

	register(state, part, motion)
end

const function refresh(state: RegistryState, part: Part): ()
	validatePartInstance(part)
	const record = state.records[part]
	if not record then
		error("Collisions: Refresh requires registration", 2)
	end

	validateRetained(state, part)
	if record.motion == "Static" then
		const box = snapshotBox(part.CFrame, part.Size)
		removeStatic(state, record)
		storeStatic(state, record, box)
	end
end

const function flushDirty(state: RegistryState): ()
	if next(state.dirty) == nil then
		return
	end

	-- Leave unprocessed rows dirty if an invalid changed Part raises an error.
	const pending: DirtyRecords = table.clone(state.dirty)
	for part, record in pending do
		if state.records[part] == record and record.motion == "Static" then
			refresh(state, part)
		else
			state.dirty[part] = nil
		end
	end
end

const function eligible(state: RegistryState, part: Part, motion: Motion): boolean
	const record = state.records[part]
	if not record or record.motion ~= motion then
		return false
	end
	if not part:IsDescendantOf(Workspace) then
		unregister(state, part)
		return false
	end
	if part.Shape ~= Enum.PartType.Block then
		unregister(state, part)
		error("Collisions: registered Part is no longer Block; registration removed", 2)
	end

	return true
end

const function clear(state: RegistryState): ()
	for _, record in state.records do
		disconnect(record.connections)
		disconnect(record.staticConnections)
	end
	table.clear(state.records)
	table.clear(state.static.parts)
	table.clear(state.static.indices)
	table.clear(state.dynamic.parts)
	table.clear(state.dynamic.indices)
	table.clear(state.dirty)
	state.static.count = 0
	state.dynamic.count = 0
	state.unsupportedStaticCount = 0
	clearGrid(state.grid)
	table.clear(state.scratch.selected)
	table.clear(state.scratch.visited)
end

const function engineParams(filter: FilterSnapshot): OverlapParams
	const params = OverlapParams.new()
	params.MaxParts = 0
	params.Tolerance = filter.tolerance
	params.RespectCanCollide = filter.respectCanCollide
	params.BruteForceAllSlow = filter.bruteForceAllSlow
	params.CollisionGroup = filter.collisionGroup

	return params
end

const function originalFilterHits(cframe: CFrame, size: Vector3, filter: FilterSnapshot): EngineFilterHits?
	if not filter.engineFilterRequired then
		return nil
	end

	-- Creator Docs' broad exclude priority conflicts with the Physics Team's
	-- nearest-ancestor mixed-list explanation. Legacy/modern interaction is also
	-- not established by these sources. Replay the snapshot on a private object
	-- and let the engine resolve those profiles; never impose both interpretations.
	const params = engineParams(filter)
	params.FilterType = filter.legacyType
	params.FilterDescendantsInstances = filter.legacyEntries
	if filter.include then
		params.IncludeInstances = filter.include
	end
	if filter.exclude then
		params.ExcludeInstances = filter.exclude
	end

	const hits: EngineFilterHits = {}
	for _, part in Workspace:GetPartBoundsInBox(cframe, size, params) do
		hits[part] = true
	end

	return hits
end

const function boxBounds(
	state: RegistryState, motion: Motion, cframe: CFrame, size: Vector3, filter: FilterSnapshot
): {Part}
	const set = if motion == "Static" then state.static else state.dynamic
	const selected = state.scratch.selected
	-- Eligibility may swap-remove a departed Part. Revisit its replacement.
	local index = 1
	while index <= set.count do
		const part = set.parts[index]
		if eligible(state, part, motion) then
			table.insert(selected, part)
			index += 1
		end
	end
	if #selected == 0 then
		return {}
	end

	const params = engineParams(filter)
	params.IncludeInstances = selected
	const filterHits = originalFilterHits(cframe, size, filter)
	const hits: {Part} = {}
	const seen: {[Part]: boolean} = {}
	for _, candidate in Workspace:GetPartBoundsInBox(cframe, size, params) do
		-- An include Part also includes its descendants. Require exact identity.
		if candidate:IsA("Part") and not seen[candidate] and eligible(state, candidate, motion)
			and accepts(candidate, filter, filterHits) then
			seen[candidate] = true
			table.insert(hits, candidate)
			if filter.maxParts > 0 and #hits >= filter.maxParts then
				break
			end
		end
	end

	return hits
end

const function gridProfile(state: RegistryState, filter: FilterSnapshot): boolean
	if filter.engineFilterRequired or filter.maxParts ~= 0 or filter.tolerance ~= 0
		or filter.respectCanCollide or filter.bruteForceAllSlow or filter.collisionGroup ~= "Default"
		or state.unsupportedStaticCount ~= 0 then
		return false
	end

	-- Read the matrix for this world on each grid query. Never configure groups.
	-- Unavailable API/access also selects BoxBounds.
	const ok, collidable = pcall(function(): boolean
		const world = Workspace :: CollisionMatrixReader
		return world:CollisionGroupsAreCollidable("Default", "Default")
	end)

	return ok and collidable == true
end

const function queryParts(
	state: RegistryState, config: ResolvedConfig, motion: Motion,
	cframe: CFrame, size: Vector3, params: OverlapParams?
): {Part}
	validateBox(cframe, size)
	const filter = snapshotFilter(params)
	if motion == "Static" then
		flushDirty(state)
		-- O(1) policy count before arbitrary descendant filtering, without a probe.
		if state.static.count > config.StaticGridThreshold and gridProfile(state, filter) then
			const hits = collectGrid(state.grid, state.scratch, snapshotBox(cframe, size), function(part: Part): boolean
				return eligible(state, part, "Static") and part.CanQuery
					and part.CollisionGroup == "Default" and accepts(part, filter, nil)
			end)
			if hits then
				return hits
			end
		end
	end

	return boxBounds(state, motion, cframe, size, filter)
end

const function getParts(
	state: RegistryState, config: ResolvedConfig, motion: Motion,
	cframe: CFrame, size: Vector3, params: OverlapParams?
): {Part}
	-- All operations are serial and non-yielding. Always release private scratch
	-- references, including when validation, dirty refresh, or an engine call fails.
	const ok, result = pcall(queryParts, state, config, motion, cframe, size, params)
	table.clear(state.scratch.selected)
	table.clear(state.scratch.visited)
	if not ok then
		error(result, 0)
	end

	return result
end

const Collisions: API = {
	Configure = function(config: Config): ()
		configuration = resolveConfig(config, configuration)
	end,
	Register = function(part: Part, motion: Motion): ()
		register(registry, part, motion)
	end,
	Unregister = function(part: Part): ()
		validatePartInstance(part)
		unregister(registry, part)
	end,
	SetMotion = function(part: Part, motion: Motion): ()
		setMotion(registry, part, motion)
	end,
	Refresh = function(part: Part): ()
		refresh(registry, part)
	end,
	StaticGetPartsIn = function(cframe: CFrame, size: Vector3, overlapParams: OverlapParams?): {Part}
		return getParts(registry, configuration, "Static", cframe, size, overlapParams)
	end,
	DynamicGetPartsIn = function(cframe: CFrame, size: Vector3, overlapParams: OverlapParams?): {Part}
		return getParts(registry, configuration, "Dynamic", cframe, size, overlapParams)
	end,
	Clear = function(): ()
		clear(registry)
	end,
}

return Collisions
