-- Server collision groups. Call from serial server code; requiring has no effects.
-- Register groups before Set, Track, BindTag, or SetCollidable.
-- Track/BindTag return idempotent stop functions. Stopping retains assignments.
-- Overlapping assignments use the last write; this module does not enforce them.

const CollectionService = game:GetService("CollectionService")
const RunService = game:GetService("RunService")
const Workspace = game:GetService("Workspace")

const m = {}

const function requireServer()
	if not RunService:IsServer() then
		error("Collisions requires a server caller", 3)
	end
end

const function validateName(name: string)
	if type(name) ~= "string" or #name == 0 or #name > 100 then
		error("Collisions group must be a nonempty string of at most 100 bytes", 3)
	end
end

const function isRegistered(name: string): boolean
	const success, result = pcall(Workspace.IsCollisionGroupRegistered, Workspace, name)
	if not success then
		error(result, 3)
	end

	return result
end

const function requireGroup(name: string)
	validateName(name)
	if not isRegistered(name) then
		error(`Collisions group is not registered: {name}`, 3)
	end
end

const function validateRoot(root: Instance)
	if typeof(root) ~= "Instance" then
		error("Collisions root must be an Instance", 3)
	end
end

const function assign(instance: Instance, group: string)
	if instance:IsA("BasePart") then
		instance.CollisionGroup = group
	end
end

-- Existing groups, including Default, are preserved.
function m:Register(group: string): ()
	requireServer()
	validateName(group)
	if not isRegistered(group) then
		const success, message = pcall(Workspace.RegisterCollisionGroup, Workspace, group)
		if not success then
			error(message, 2)
		end
	end
end

function m:SetCollidable(first: string, second: string, collidable: boolean): ()
	requireServer()
	requireGroup(first)
	requireGroup(second)
	if type(collidable) ~= "boolean" then
		error("Collisions collidable must be a boolean", 2)
	end

	const success, message = pcall(Workspace.CollisionGroupSetCollidable, Workspace, first, second, collidable)
	if not success then
		error(message, 2)
	end
end

-- Assign the root, if it is a part, and all existing descendant parts.
function m:Set(root: Instance, group: string): ()
	requireServer()
	validateRoot(root)
	requireGroup(group)
	assign(root, group)
	for _, descendant in root:GetDescendants() do
		assign(descendant, group)
	end
end

-- Also assign future descendants. Call stop when the owner releases the root.
function m:Track(root: Instance, group: string): () -> ()
	requireServer()
	validateRoot(root)
	requireGroup(group)
	local active = true
	const connections: { RBXScriptConnection } = {}

	const function stop()
		if not active then
			return
		end

		active = false
		for _, connection in connections do
			connection:Disconnect()
		end
		table.clear(connections)
	end

	connections[1] = root.DescendantAdded:Connect(function(descendant)
		if active and descendant:IsDescendantOf(root) then
			assign(descendant, group)
		end
	end)
	connections[2] = root.Destroying:Connect(stop)
	const success, message = pcall(m.Set, m, root, group)
	if not success then
		stop()
		error(message, 2)
	end

	return stop
end

-- Track tagged roots in the DataModel. Tag removal stops that root's tracking.
-- The caller owns this binding and must call stop at teardown.
function m:BindTag(tag: string, group: string): () -> ()
	requireServer()
	requireGroup(group)
	if type(tag) ~= "string" or #tag == 0 then
		error("Collisions tag must be a nonempty string", 2)
	end

	local active = true
	const roots: { [Instance]: () -> () } = {}
	const connections: { RBXScriptConnection } = {}

	const function remove(root: Instance)
		const stop = roots[root]
		if stop then
			roots[root] = nil
			stop()
		end
	end

	const function add(root: Instance)
		if not active or roots[root] or not CollectionService:HasTag(root, tag) or not root:IsDescendantOf(game) then
			return
		end

		roots[root] = m:Track(root, group)
	end

	const function stop()
		if not active then
			return
		end

		active = false
		for _, connection in connections do
			connection:Disconnect()
		end
		table.clear(connections)
		for root in roots do
			remove(root)
		end
	end

	connections[1] = CollectionService:GetInstanceAddedSignal(tag):Connect(add)
	connections[2] = CollectionService:GetInstanceRemovedSignal(tag):Connect(function(root)
		if not CollectionService:HasTag(root, tag) or not root:IsDescendantOf(game) then
			remove(root)
		end
	end)
	const success, message = pcall(function()
		for _, root in CollectionService:GetTagged(tag) do
			add(root)
		end
	end)
	if not success then
		stop()
		error(message, 2)
	end

	return stop
end

return m
