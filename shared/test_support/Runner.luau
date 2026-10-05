-- Owns readiness, bounded execution, capture control, collection and cleanup.
local RunService = game:GetService("RunService")
local Codec = require(script.Parent.Codec)
local Runner = {}

local function bound(value, default, maximum)
	value = if value == nil then default else value
	assert(type(value) == "number" and value == value and value > 0 and value <= maximum, "invalid bound")
	return value
end

function Runner.run(driver, spec)
	local side = if RunService:IsServer() then "SERVER" else "CLIENT"
	local prefix = side .. "|" .. driver.Name .. "|"
	local run = assert(driver:GetAttribute("RunId"), "RunId required")
	local timeout = bound(spec.timeout, 60, 600)
	local readyTimeout = bound(spec.readyTimeout, 30, 600)
	local captureTimeout = bound(spec.captureTimeout, 30, 120)
	local collectionTimeout = bound(spec.collectionTimeout, 30, 300)
	local cleanupTimeout = bound(spec.cleanupTimeout, 5, 30)
	local spikeLimit = bound(spec.spikeLimit, 128, 256)
	assert(spikeLimit % 1 == 0, "integer spike limit required")
	local result = { id = spec.id, status = "unrun", passed = 0, failed = 0, skipped = 0, reason = "no assertions", metrics = {} }
	local owned = {}
	local cleaned = false
	local started = false
	local executionDeadline
	local state = "readiness"
	local context = {}
	local function setState(value)
		state = value
		driver:SetAttribute("State", value)
	end
	local function cleanup()
		if cleaned then return end
		cleaned = true
		local slice = cleanupTimeout / math.max(1, #owned)
		for index = #owned, 1, -1 do
			local done, ok, why = false, false, "cleanup timeout"
			local thread = task.spawn(function()
				ok, why = pcall(owned[index])
				done = true
			end)
			local deadline = os.clock() + slice
			while not done and os.clock() < deadline do task.wait() end
			if not done then task.cancel(thread) end
			if not done or not ok then
				result.status = "fail"
				result.failed += 1
				result.reason = Codec.reason("cleanup: " .. tostring(why))
			end
		end
		table.clear(owned)
	end
	function context:own(release)
		assert(not cleaned and #owned < 512, "ownership closed or limit reached")
		table.insert(owned, release)
	end
	function context:instance(instance)
		self:own(function() instance:Destroy() end)
		return instance
	end
	function context:connection(connection)
		self:own(function() connection:Disconnect() end)
		return connection
	end
	function context:task(thread)
		self:own(function()
			if coroutine.status(thread) ~= "dead" then task.cancel(thread) end
		end)
		return thread
	end
	function context:restore(object, key, value)
		local before = object[key]
		object[key] = value
		self:own(function()
			if object[key] == value then object[key] = before end
		end)
	end
	function context:check(condition, why)
		if condition then result.passed += 1 else
			result.failed += 1
			result.reason = Codec.reason(why)
		end
	end
	function context:metric(method, workload, kind, thresholdMs)
		assert(state ~= "measurement", "declare metrics before measurement")
		assert(kind == "script" or kind == "scheduling" or kind == "setup" or kind == "teardown", "unsupported timing kind")
		local threshold = math.floor(bound(thresholdMs, nil, 600000) * 1000 + 0.5)
		assert(threshold > 0, "threshold below precision")
		for _, existing in result.metrics do
			assert(existing.method ~= method or existing.workload ~= workload or existing.kind ~= kind, "duplicate metric")
		end
		assert(#result.metrics < 32, "metric limit")
		local metric = { method = method, workload = workload, kind = kind, threshold = threshold,
			count = 0, total = 0, maximum = 0, window = 0, spikeCount = 0, overflow = 0, spikes = {} }
		table.insert(result.metrics, metric)
		return metric
	end
	function context:observe(metric, seconds)
		assert(state ~= "capture-waiting", "capture samples must not alter measurement totals")
		assert(seconds == seconds and seconds >= 0 and seconds <= 600, "invalid duration")
		local duration = math.floor(seconds * 1000000 + 0.5)
		metric.count += 1
		metric.total += duration
		metric.maximum = math.max(metric.maximum, duration)
		if duration > metric.threshold then
			metric.spikeCount += 1
			if #metric.spikes < spikeLimit then
				table.insert(metric.spikes, { metric.count, duration })
			else metric.overflow += 1 end
		end
	end
	function context:measure(metric, callback)
		local begin = os.clock()
		callback()
		self:observe(metric, os.clock() - begin)
	end
	function context:scope(method, workload, index)
		return "Harness/" .. run .. "/" .. spec.id .. "/" .. method .. "/" .. workload .. "/" .. (if state == "capture-waiting" then "sample" else "measurement") .. "/" .. tostring(index)
	end
	setState("readiness")
	driver:SetAttribute("WorkloadState", "unexecuted")
	driver:SetAttribute("ProfilerState", if spec.capture then "awaiting-capture" else "not-required")
	local function waitFlag(flag, seconds)
		local deadline = os.clock() + seconds
		repeat
			if driver:GetAttribute("Cancel") then error("cancelled", 0) end
			if driver:GetAttribute(flag) then return true end
			task.wait(0.05)
		until os.clock() >= deadline
		return false
	end
	local workerDone = false
	local workerError
	local worker = task.spawn(function()
		local ok, why = pcall(function()
			assert(waitFlag("Ready", readyTimeout), "readiness timeout")
			started = true
			executionDeadline = os.clock() + timeout
			setState("setup")
			local setupBegin = os.clock()
			if spec.setup then spec.setup(context) end
			local setupWindow = math.floor((os.clock() - setupBegin) * 1000000 + 0.5)
			for _, metric in result.metrics do
				if metric.kind == "setup" then metric.window = setupWindow end
			end
			setState("warm-up")
			if spec.warmup then spec.warmup(context) end
			for _, metric in result.metrics do
				if metric.kind == "script" or metric.kind == "scheduling" then
					metric.count, metric.total, metric.maximum = 0, 0, 0
					metric.spikeCount, metric.overflow = 0, 0
					table.clear(metric.spikes)
				end
			end
			setState("measurement")
			driver:SetAttribute("WorkloadState", "running")
			local begin = os.clock()
			spec.workload(context)
			local window = math.floor((os.clock() - begin) * 1000000 + 0.5)
			for _, metric in result.metrics do
				if metric.kind == "script" or metric.kind == "scheduling" then metric.window = window end
			end
			driver:SetAttribute("WorkloadState", "complete")
			if spec.capture then
				setState("capture-waiting")
				print(prefix .. "CTRL|PAUSE NOW FOR MICROPROFILER")
				local deadline = os.clock() + captureTimeout
				repeat
					if driver:GetAttribute("Cancel") then error("cancelled", 0) end
					if driver:GetAttribute("CaptureDone") then break end
					if spec.continueCapture then spec.continueCapture(context) end
					task.wait()
				until os.clock() >= deadline
				driver:SetAttribute("ProfilerState", "awaiting-review")
			end
		end)
		workerError = if ok then nil else why
		workerDone = true
	end)
	local deadline = os.clock() + readyTimeout + timeout
	while not workerDone and not driver:GetAttribute("Cancel") and os.clock() < (executionDeadline or deadline) do
		task.wait(0.05)
	end
	if not workerDone then
		task.cancel(worker)
		result.status = if driver:GetAttribute("Cancel") then "cancelled" else "timeout"
		result.reason = result.status .. " in " .. state
	elseif workerError then
		result.status = if driver:GetAttribute("Cancel") then "cancelled" elseif string.find(tostring(workerError), "readiness timeout", 1, true) then "timeout" else "fail"
		result.failed += 1
		result.reason = Codec.reason(workerError)
	else
		result.status = if result.failed > 0 then "fail" elseif result.passed > 0 then "pass" else "unrun"
		if result.status == "pass" then result.reason = "-" end
	end
	if started and driver:GetAttribute("WorkloadState") ~= "complete" then driver:SetAttribute("WorkloadState", result.status) end
	setState("collection")
	local cleanupBegin = os.clock()
	cleanup()
	local cleanupWindow = math.floor((os.clock() - cleanupBegin) * 1000000 + 0.5)
	for _, metric in result.metrics do
		if metric.kind == "teardown" then metric.window = cleanupWindow end
	end
	-- Zero-count metrics were never measured. Do not serialize them as observations.
	for index = #result.metrics, 1, -1 do
		if result.metrics[index].count == 0 then table.remove(result.metrics, index) end
	end
	local ok, records = pcall(function() return Codec.records(side, driver.Name, run, Codec.encode(result)) end)
	if ok then
		for _, record in records do print(record) end
	else
		print(prefix .. "FAIL|" .. Codec.reason(records))
	end
	-- Capture saving/retrieval owns Play. A collection timeout is not a Stop request.
	local waitOk, collected = pcall(waitFlag, "Collected", collectionTimeout)
	collected = waitOk and collected
	driver:SetAttribute("CollectionState", if driver:GetAttribute("Cancel") then "cancelled" elseif collected then "complete" else "timeout")
	setState(if driver:GetAttribute("Cancel") then "cancelled" elseif collected then "completion" else "timeout")
	return result
end

return Runner
