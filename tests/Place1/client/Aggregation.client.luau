-- H03: Do aggregation and serialization retain weighted totals, spikes and overflow?
-- Supplied duration fixtures, not engine performance measurements. Stop after round trip inputs.
if not script:GetAttribute("RunId") then return end
local Runner = require(script.Parent.TestSupport.Runner)
local metric
Runner.run(script, {
	id = "H03",
	spikeLimit = 1,
	setup = function(context)
		metric = context:metric("fixture", "known-durations", "script", 3)
	end,
	warmup = function(context)
		context:observe(metric, 0.100)
	end,
	workload = function(context)
		context:observe(metric, 0.002)
		context:observe(metric, 0.008)
		context:observe(metric, 0.008)
		context:check(metric.count == 3 and metric.total == 18000 and metric.maximum == 8000, "duration totals")
		context:check(metric.spikeCount == 2 and metric.overflow == 1 and metric.spikes[1][1] == 2 and metric.spikes[1][2] == 8000, "spike storage")
	end,
})
