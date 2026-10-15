-- C01: Does tracking release listeners and reject stale queued assignments?
-- Native doubles exercise module logic, not Roblox physics or signal behavior.
return function(loadPackage)
	const signals = {}
	const function signal()
		const listeners = {}
		const pending = {}
		const event = {}
		function event:Connect(callback)
			const connection = { Connected = true }
			function connection:Disconnect()
				self.Connected = false
			end
			listeners[connection] = callback
			return connection
		end
		function event:Fire(value)
			for connection, callback in listeners do
				if connection.Connected then
					table.insert(pending, { connection, callback, value })
				end
			end
		end
		function event:Flush()
			while #pending > 0 do
				const item = table.remove(pending, 1)
				if item[1].Connected then
					item[2](item[3])
				end
			end
		end
		function event:Count()
			local count = 0
			for connection in listeners do
				if connection.Connected then count += 1 end
			end
			return count
		end
		table.insert(signals, event)
		return event
	end

	const function instance(class, parent)
		const object = {
			_instance = true, Parent = parent, children = {}, CollisionGroup = "Default",
			DescendantAdded = signal(), Destroying = signal(),
		}
		function object:IsA(name)
			return class == name or (name == "BasePart" and class == "Part")
		end
		function object:IsDescendantOf(ancestor)
			local current = self.Parent
			while current do
				if current == ancestor then return true end
				current = current.Parent
			end
			return false
		end
		function object:GetDescendants()
			const result = {}
			const function visit(root)
				for _, child in root.children do
					table.insert(result, child)
					visit(child)
				end
			end
			visit(self)
			return result
		end
		if parent then table.insert(parent.children, object) end
		return object
	end

	const game = instance("DataModel")
	const workspace = instance("Workspace", game)
	const groups = { Default = true }
	local registrations = 0
	local server = true
	local collidable = true
	function workspace:IsCollisionGroupRegistered(name) return groups[name] == true end
	function workspace:RegisterCollisionGroup(name)
		assert(not groups[name])
		groups[name] = true
		registrations += 1
	end
	function workspace:CollisionGroupSetCollidable(first, second, value)
		assert(groups[first] and groups[second])
		collidable = value
	end
	const tagged = {}
	const added = signal()
	const removed = signal()
	const collection = {}
	function collection:HasTag(root) return tagged[root] == true end
	function collection:GetTagged()
		const result = {}
		for root in tagged do table.insert(result, root) end
		return result
	end
	function collection:GetInstanceAddedSignal() return added end
	function collection:GetInstanceRemovedSignal() return removed end
	const services = {
		Workspace = workspace, CollectionService = collection,
		RunService = { IsServer = function() return server end },
	}
	function game:GetService(name) return assert(services[name]) end
	const module = loadPackage(game, function(value)
		return if type(value) == "table" and value._instance then "Instance" else typeof(value)
	end)
	assert(registrations == 0, "require must not register groups")
	module:Register("Actors")
	module:Register("Actors")
	module:Register("Default")
	assert(registrations == 1)
	module:SetCollidable("Actors", "Actors", false)
	assert(not collidable)
	assert(not pcall(module.SetCollidable, module, "Actors", "Missing", true))
	assert(not pcall(module.Register, module, ""))
	server = false
	assert(not pcall(module.Register, module, "Client"))
	server = true

	const root = instance("Model", workspace)
	const child = instance("Part", root)
	const nested = instance("Folder", root)
	const grandchild = instance("Part", nested)
	const stop = module:Track(root, "Actors")
	assert(child.CollisionGroup == "Actors" and grandchild.CollisionGroup == "Actors")
	const late = instance("Part", root)
	root.DescendantAdded:Fire(late)
	root.DescendantAdded:Flush()
	assert(late.CollisionGroup == "Actors")
	const stale = instance("Part", root)
	root.DescendantAdded:Fire(stale)
	stale.Parent = nil
	root.DescendantAdded:Flush()
	assert(stale.CollisionGroup == "Default", "removed descendants must be ignored")
	const queued = instance("Part", root)
	root.DescendantAdded:Fire(queued)
	stop()
	stop()
	root.DescendantAdded:Flush()
	assert(queued.CollisionGroup == "Default")
	assert(child.CollisionGroup == "Actors", "stop must retain assignments")

	const taggedRoot = instance("Model", workspace)
	const taggedPart = instance("Part", taggedRoot)
	tagged[taggedRoot] = true
	const stopTag = module:BindTag("Actors", "Actors")
	assert(taggedPart.CollisionGroup == "Actors")
	added:Fire(taggedRoot)
	added:Flush()
	assert(taggedRoot.DescendantAdded:Count() == 1, "duplicate tag delivery must not duplicate tracking")
	tagged[taggedRoot] = nil
	removed:Fire(taggedRoot)
	removed:Flush()
	const afterRemoval = instance("Part", taggedRoot)
	taggedRoot.DescendantAdded:Fire(afterRemoval)
	taggedRoot.DescendantAdded:Flush()
	assert(afterRemoval.CollisionGroup == "Default")
	tagged[taggedRoot] = true
	added:Fire(taggedRoot)
	added:Flush()
	assert(afterRemoval.CollisionGroup == "Actors")
	stopTag()
	stopTag()
	const destroyRoot = instance("Model", workspace)
	module:Track(destroyRoot, "Actors")
	destroyRoot.Destroying:Fire()
	destroyRoot.Destroying:Flush()
	const brokenRoot = instance("Model", workspace)
	function brokenRoot:GetDescendants() error("fixture setup failure") end
	assert(not pcall(module.Track, module, brokenRoot, "Actors"))
	for _, event in signals do
		assert(event:Count() == 0, "tracking leaked a connection")
	end
	print("C01 pass")
end
