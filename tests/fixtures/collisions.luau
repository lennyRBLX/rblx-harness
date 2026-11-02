-- C01: Do registry replacements, motion transfers and removal release owned callbacks?
-- Controlled query hits and queued callbacks test ownership, not engine behavior.
return function(loadPackage)
	const signals = {}
	const function signal()
		const listeners, pending = {}, {}
		const event = {}
		function event:Connect(callback)
			const connection = {Connected = true}
			function connection:Disconnect() self.Connected = false end
			listeners[connection] = callback
			return connection
		end
		function event:Fire(value)
			for connection, callback in listeners do
				if connection.Connected then table.insert(pending, {callback, value}) end
			end
		end
		function event:Flush()
			-- Stress record ownership by invoking callbacks captured before disconnect.
			while #pending > 0 do
				const item = table.remove(pending, 1)
				item[1](item[2])
			end
		end
		function event:Count()
			local count = 0
			for connection in listeners do if connection.Connected then count += 1 end end
			return count
		end
		table.insert(signals, event)
		return event
	end

	const Vector3 = {}
	const vectorMethods = {}
	const vectorMeta = {__index = vectorMethods}
	function Vector3.new(x, y, z)
		return setmetatable({_type = "Vector3", X = x, Y = y, Z = z}, vectorMeta)
	end
	function vectorMeta.__add(a, b) return Vector3.new(a.X + b.X, a.Y + b.Y, a.Z + b.Z) end
	function vectorMeta.__sub(a, b) return Vector3.new(a.X - b.X, a.Y - b.Y, a.Z - b.Z) end
	function vectorMeta.__mul(a, b) return Vector3.new(a.X * b, a.Y * b, a.Z * b) end
	function vectorMethods:Dot(b) return self.X * b.X + self.Y * b.Y + self.Z * b.Z end
	const function cframe(x)
		const frame = {
			_type = "CFrame", Position = Vector3.new(x, 0, 0),
			XVector = Vector3.new(1, 0, 0), YVector = Vector3.new(0, 1, 0), ZVector = Vector3.new(0, 0, 1),
		}
		function frame:GetComponents() return self.Position.X, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1 end
		return frame
	end
	const Enum = {PartType = {Block = "Block", Ball = "Ball"}, RaycastFilterType = {Include = "Include", Exclude = "Exclude"}}
	const OverlapParams = {}
	function OverlapParams.new()
		return {
			_type = "OverlapParams", FilterType = Enum.RaycastFilterType.Exclude,
			FilterDescendantsInstances = {}, MaxParts = 0, Tolerance = 0,
			RespectCanCollide = false, BruteForceAllSlow = false, CollisionGroup = "Default",
		}
	end
	const function instance(class, parent)
		const object = {
			_type = "Instance", Parent = parent, Destroying = signal(), properties = {},
			Shape = Enum.PartType.Block, CFrame = cframe(0), Size = Vector3.new(2, 2, 2),
			CanQuery = true, CollisionGroup = "Default",
		}
		function object:IsA(name) return class == name end
		function object:IsDescendantOf(ancestor)
			local current = self.Parent
			while current do
				if current == ancestor then return true end
				current = current.Parent
			end
			return false
		end
		function object:GetPropertyChangedSignal(name)
			if not self.properties[name] then self.properties[name] = signal() end
			return self.properties[name]
		end
		return object
	end
	const workspace = instance("Workspace")
	workspace.DescendantRemoving = signal()
	local engineHits, queryError = {}, false
	function workspace:GetPartBoundsInBox()
		if queryError then error("query failure") end
		return table.clone(engineHits)
	end
	const game = {}
	function game:GetService(name) assert(name == "Workspace"); return workspace end
	const module = loadPackage(game, function(value)
		return if type(value) == "table" and value._type then value._type else typeof(value)
	end, Vector3, Enum, OverlapParams)
	const function expect(query, expected)
		const actual = query(cframe(0), Vector3.new(10, 10, 10))
		assert(#actual == #expected, "wrong membership count")
		const seen = {}
		for _, part in actual do
			assert(not seen[part] and table.find(expected, part), "duplicate or unregistered hit")
			seen[part] = true
		end
		return actual
	end
	const function connections(expected)
		local count = 0
		for _, event in signals do count += event:Count() end
		if expected ~= nil then assert(count == expected, "leaked or duplicate callbacks") end
		return count
	end
	connections(0)
	const first = instance("Part", workspace)
	const second = instance("Part", workspace)
	const unregistered = instance("Part", first)
	engineHits = {first, second, first, unregistered}
	module.Register(first, "Static")
	module.Register(second, "Dynamic")
	expect(module.StaticGetPartsIn, {first})
	expect(module.DynamicGetPartsIn, {second})
	const owned = connections()

	module.Register(first, "Static")
	connections(owned)
	assert(first.Destroying:Count() == 1)
	assert(not pcall(module.Register, first, "invalid"))
	expect(module.StaticGetPartsIn, {first})
	connections(owned)
	module.SetMotion(first, "Dynamic")
	expect(module.StaticGetPartsIn, {})
	expect(module.DynamicGetPartsIn, {first, second})
	for _, event in first.properties do assert(event:Count() == 0) end
	assert(connections() < owned, "motion transfer retained static callbacks")
	module.SetMotion(second, "Static")
	second.CFrame = cframe(20)
	module.Refresh(second)
	second:GetPropertyChangedSignal("CFrame"):Fire()
	second:GetPropertyChangedSignal("CFrame"):Flush()
	expect(module.StaticGetPartsIn, {second})
	connections(owned)
	const result = expect(module.DynamicGetPartsIn, {first})
	table.clear(result)
	expect(module.DynamicGetPartsIn, {first})

	-- A delayed removal belongs to the old registration, not its replacement.
	workspace.DescendantRemoving:Fire(first)
	module.Register(first, "Dynamic")
	workspace.DescendantRemoving:Flush()
	expect(module.DynamicGetPartsIn, {first})
	connections(owned)
	workspace.DescendantRemoving:Fire(first)
	first.Parent = nil
	workspace.DescendantRemoving:Flush()
	expect(module.DynamicGetPartsIn, {})
	const retained = connections()
	first.Parent = workspace
	expect(module.DynamicGetPartsIn, {})
	assert(not pcall(module.SetMotion, first, "Dynamic"))
	module.Register(first, "Dynamic")
	expect(module.DynamicGetPartsIn, {first})

	-- Queries also prune departures before an event is delivered.
	first.Parent = nil
	expect(module.DynamicGetPartsIn, {})
	first.Parent = workspace
	expect(module.DynamicGetPartsIn, {})
	module.Register(first, "Dynamic")
	first.Destroying:Fire()
	first.Destroying:Flush()
	expect(module.DynamicGetPartsIn, {})
	module.Unregister(first)
	connections(retained)
	second.Shape = Enum.PartType.Ball
	assert(not pcall(module.Refresh, second))
	expect(module.StaticGetPartsIn, {})
	connections(0)

	second.Shape = Enum.PartType.Block
	module.Register(first, "Dynamic")
	module.Register(second, "Static")
	queryError = true
	assert(not pcall(module.DynamicGetPartsIn, cframe(0), Vector3.new(10, 10, 10)))
	queryError = false
	expect(module.DynamicGetPartsIn, {first})
	second:GetPropertyChangedSignal("CFrame"):Fire()
	workspace.DescendantRemoving:Fire(first)
	module.Clear()
	module.Clear()
	second:GetPropertyChangedSignal("CFrame"):Flush()
	workspace.DescendantRemoving:Flush()
	connections(0)
	expect(module.StaticGetPartsIn, {})
	expect(module.DynamicGetPartsIn, {})
	module.Register(first, "Dynamic")
	expect(module.DynamicGetPartsIn, {first})
	module.Clear()
	connections(0)
	print("C01 pass")
end
