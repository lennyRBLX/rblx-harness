-- H01: Does shared support preserve runtime identity and release only owned resources?
-- Stop after bounded lifecycle cases and a codec vector. No spatial workload or capture.
if not script:GetAttribute("RunId") then return end
local Support = script.Parent.TestSupport
local Runner = require(Support.Runner)
local Codec = require(Support.Codec)
local RunService = game:GetService("RunService")

Runner.run(script, {
	id = "H01",
	timeout = 10,
	workload = function(context)
		context:check(not RunService:IsServer(), "LocalScript did not run on client")
		local payload = Codec.encode({ id = "VECTOR", status = "pass", passed = 1, failed = 0, skipped = 0, metrics = {} })
		context:check(buffer.tostring(payload) == "HTB1\nR\tVECTOR\tpass\t1\t0\t0\t-\n", "buffer vector differs")
		local records = Codec.records("CLIENT", "Vector", "vector1", payload)
		context:check(#records == 1 and string.find(records[1], "CLIENT|Vector|BUF|1|vector1|1|1|", 1, true) == 1, "transport prefix differs")
		local unrelated = context:instance(Instance.new("Folder"))
		unrelated.Name = "Unrelated"
		unrelated.Parent = workspace
		for _, mode in { "cancel", "timeout", "complete", "capture", "failure", "readiness", "cleanup" } do
			local driver = context:instance(Instance.new("Folder"))
			driver.Name = "Lifecycle-" .. mode
			driver.Parent = script
			driver:SetAttribute("RunId", script:GetAttribute("RunId") .. "-" .. mode)
			driver:SetAttribute("Ready", mode ~= "readiness")
			driver:SetAttribute("Collected", true)
			local released = 0
			local fixture
			local connection
			local ownedThread
			local continuation = 0
			local stateObserved = false
			local outcome = Runner.run(driver, {
				id = "H01-" .. mode,
				readyTimeout = 0.1,
				cleanupTimeout = 0.1,
				timeout = if mode == "timeout" then 0.15 else 2,
				capture = mode == "capture",
				captureTimeout = 0.15,
				setup = function(inner)
					fixture = inner:instance(Instance.new("Folder"))
					fixture.Parent = workspace
					connection = inner:connection(RunService.Heartbeat:Connect(function() end))
					ownedThread = inner:task(task.spawn(function() task.wait(10) end))
					inner:own(function() released += 1 end)
					if mode == "cleanup" then inner:own(function() task.wait(10) end) end
					inner:restore(unrelated, "Name", "OwnedName")
					unrelated.Name = "LaterOwner"
				end,
				workload = function(inner)
					inner:check(true, "workload reached")
					if mode == "failure" then error("controlled failure", 0) end
					if mode == "cancel" then
						inner:task(task.delay(0.05, function() driver:SetAttribute("Cancel", true) end))
						task.wait(10)
					elseif mode == "timeout" then task.wait(10) end
				end,
				continueCapture = function()
					continuation += 1
					stateObserved = driver:GetAttribute("State") == "capture-waiting" and fixture.Parent == workspace
				end,
			})
			local expected = if mode == "cancel" then "cancelled" elseif mode == "timeout" or mode == "readiness" then "timeout" elseif mode == "failure" or mode == "cleanup" then "fail" else "pass"
			context:check(outcome.status == expected, mode .. " status")
			if mode == "readiness" then
				context:check(fixture == nil and released == 0, "readiness mutated fixtures")
			else
				context:check(released == 1 and fixture.Parent == nil and not connection.Connected and coroutine.status(ownedThread) == "dead", mode .. " owned cleanup")
			end
			context:check(unrelated.Parent == workspace and unrelated.Name == "LaterOwner", mode .. " ownership restore")
			if mode == "capture" then
				context:check(continuation > 0 and stateObserved, "capture continuation missing")
				context:check(driver:GetAttribute("WorkloadState") == "complete" and driver:GetAttribute("ProfilerState") == "awaiting-review", "capture completion conflated")
			end
		end
	end,
})
