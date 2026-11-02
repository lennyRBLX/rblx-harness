-- HR1: Offline contract doubles, not engine scheduling/access evidence.
return function(Core, Bridge, commands, coreSource, bridgeSource, oldSource, newSource)
	local objects, deferred, timers = {}, {}, {}
	local methods = {}
	local function instance(class, name, parent)
		local object = {class = class, Name = name or class, Parent = parent, attrs = {}, Archivable = true}
		setmetatable(object, {__index = function(self, key)
			return methods[key] or self:FindFirstChild(key)
		end})
		table.insert(objects, object)
		return object
	end
	function methods:IsA(class)
		return self.class == class or (class == "BaseScript" and (self.class == "Script" or self.class == "LocalScript"))
	end
	function methods:GetChildren()
		local children = {}
		for _, object in objects do
			if rawget(object, "Parent") == self then table.insert(children, object) end
		end
		return children
	end
	function methods:GetDescendants()
		local children = self:GetChildren()
		local result = table.clone(children)
		for _, child in children do
			for _, descendant in child:GetDescendants() do table.insert(result, descendant) end
		end
		return result
	end
	function methods:FindFirstChild(name)
		for _, child in self:GetChildren() do if child.Name == name then return child end end
		return nil
	end
	function methods:IsDescendantOf(ancestor)
		local parent = rawget(self, "Parent")
		while parent do
			if parent == ancestor then return true end
			parent = rawget(parent, "Parent")
		end
		return false
	end
	function methods:GetFullName() return self.Name end
	function methods:GetAttribute(name) return self.attrs[name] end
	function methods:SetAttribute(name, value) self.attrs[name] = value end
	function methods:GetAttributes() return table.clone(self.attrs) end
	function methods:Destroy() self.Parent = nil end
	function methods:Clone()
		local clone = instance(self.class, self.Name)
		clone.Source = self.Source
		for _, child in self:GetChildren() do child:Clone().Parent = clone end
		return clone
	end
	function methods:Invoke(request) return self.OnInvoke(request) end
	function methods:WaitForChild(name) return self:FindFirstChild(name) end
	local game = instance("DataModel")
	local container = instance("ServerScriptService", nil, game)
	local storage = instance("ReplicatedStorage", nil, game)
	local players = instance("Players", nil, game)
	local player = instance("Player", "LocalPlayer", players)
	local playerScripts = instance("PlayerScripts", nil, player)
	local target = instance("ModuleScript", "Quoted\034.\231\130\142", storage)
	target.Source = oldSource
	local runService = {}
	local server = true
	function runService:IsStudio() return true end
	function runService:IsRunning() return true end
	function runService:IsServer() return server end
	function runService:IsClient() return not server end
	local editor = {}
	function editor:GetEditorSource(object) return object.Source end
	function game:GetService(name)
		return name == "RunService" and runService or name == "ScriptEditorService" and editor or self:FindFirstChild(name)
	end
	local Instance = {new = instance}
	assert(not pcall(commands.client, game, Instance), "wrong execution side must refuse")
	server = false
	assert(commands.client(game, Instance).Status == "Booting")
	local clientRoot = playerScripts:FindFirstChild("__HarnessHotReload_HR1")
	assert(clientRoot.Runner:IsA("LocalScript"))
	server = true
	assert(commands.bootstrap(game, Instance).Status == "Booting")
	local root = container:FindFirstChild("__HarnessHotReload_HR1")
	assert(root.PatchCore.Source == coreSource and root.Runner.Source == bridgeSource)
	local exports = {Read = function() return "old" end, Removed = true}
	local consumer, cached = exports, exports.Read
	local failure, externalChange = false, false
	local function requireModule(module)
		if module == root.PatchCore then return Core end
		if module == target then return exports end
		assert(module.Source == newSource)
		if failure then error("candidate failure") end
		if externalChange then exports.External = true end
		return {Read = function() return "new" end, Added = 7}
	end
	local task = {}
	function task.defer(callback)
		local handle = {callback = callback}
		table.insert(deferred, handle)
		return handle
	end
	function task.delay(_, callback) table.insert(timers, callback) end
	function task.cancel(handle) handle.cancelled = true end
	local function flush()
		while #deferred > 0 do
			local handle = table.remove(deferred, 1)
			if not handle.cancelled then handle.callback() end
		end
		for _, timer in timers do timer() end
		table.clear(timers)
	end
	Bridge(game, root.Runner, requireModule, function(value)
		return type(value) == "table" and rawget(value, "class") and "Instance" or typeof(value)
	end, task)
	assert(commands.poll(game).Status == "Ready")
	local accepted = commands.patch(game)
	assert(accepted.Accepted and consumer.Read() == "old")
	assert(not pcall(commands.patch, game), "in-flight patch must refuse")
	flush()
	local status = commands.status(game)
	assert(status.Status == "Applied" and status.RequestId == accepted.RequestId and status.Revision == 1)
	assert(consumer == exports and consumer.Read() == "new" and cached() == "old")
	assert(consumer.Removed == nil and consumer.Added == 7 and target.Source == oldSource)
	assert(not pcall(commands.patch, game), "stale revision must refuse")
	commands.undo(game)
	flush()
	assert(consumer.Read() == "old" and consumer.Removed and consumer.Added == nil)
	commands.undo(game)
	flush()
	assert(commands.status(game).Status == "Failed" and consumer.Read() == "old")
	failure = true
	commands.patch2(game)
	flush()
	assert(commands.status(game).Status == "Failed" and consumer.Read() == "old")
	failure = false
	externalChange = true
	commands.patch2(game)
	flush()
	assert(commands.status(game).Status == "Failed" and consumer.External and consumer.Read() == "old")
	exports.External, externalChange = nil, false
	-- Rejected replacements leave the existing table intact, including NaN.
	for _, replacement in {{Nested = {}}, table.freeze({Value = 2}), setmetatable({}, {}), {[1] = 2}, {Value = 0/0}} do
		assert(not pcall(Core.Replace, exports, replacement))
		assert(consumer.Read() == "old")
	end
	-- The initial generation also detects changes during candidate evaluation.
	local first = {Value = 1}
	local expected = Core.Snapshot(first)
	first.Value = 2
	assert(not pcall(Core.Replace, first, {Value = 3}, expected) and first.Value == 2)
	-- Exhaust the retained-candidate budget with failed evaluations.
	failure = true
	while commands.status(game).RetainedCandidates < commands.status(game).CandidateLimit do
		commands.patch2(game)
		flush()
	end
	assert(not pcall(commands.patch2, game))
	-- A new bridge has an independent session budget; timeout faults mutations.
	local fresh = instance("Folder", "__HarnessHotReload_HR1", container)
	fresh:SetAttribute("Session", "HR1")
	instance("ModuleScript", "PatchCore", fresh)
	instance("BindableFunction", "Command", fresh)
	local runner = instance("Script", "Runner", fresh)
	root.Parent, root = nil, fresh
	Bridge(game, runner, requireModule, function(value)
		return type(value) == "table" and rawget(value, "class") and "Instance" or typeof(value)
	end, task)
	failure, externalChange = false, true
	commands.patch(game)
	flush()
	assert(commands.status(game).Status == "Failed" and consumer.External and consumer.Read() == "old")
	exports.External, externalChange = nil, false
	commands.patch(game)
	for _, timer in timers do timer() end
	assert(commands.status(game).Status == "TimedOut")
	flush()
	assert(not pcall(commands.patch, game) and consumer.Read() == "old")
	fresh:SetAttribute("Session", "another-playtest")
	assert(not pcall(commands.poll, game))
end
