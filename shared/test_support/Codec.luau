-- HTB1. Console transport is hex of buffer bytes, never tostring(buffer).
local Codec = {}

local function token(value)
	assert(type(value) == "string" and #value > 0 and #value <= 96 and string.match(value, "^[%w_%.:/%-]+$"), "invalid identity")
	return value
end

local function integer(value)
	assert(type(value) == "number" and value >= 0 and value <= 9007199254740991 and value % 1 == 0, "invalid integer")
	return string.format("%.0f", value)
end

function Codec.reason(value)
	return string.sub(string.gsub(tostring(value), "[^ -~]", " "):gsub("|", "/"), 1, 160)
end

function Codec.encode(result)
	local rows = { "HTB1", table.concat({ "R", token(result.id), result.status, integer(result.passed), integer(result.failed), integer(result.skipped), result.reason or "-" }, "\t") }
	for _, metric in result.metrics do
		table.insert(rows, table.concat({ "M", token(metric.method), token(metric.workload), metric.kind,
			integer(metric.count), integer(metric.total), integer(metric.maximum), integer(metric.threshold),
			integer(metric.spikeCount), integer(metric.overflow), integer(metric.window) }, "\t"))
		for _, spike in metric.spikes do
			table.insert(rows, table.concat({ "P", metric.method, metric.workload, metric.kind, integer(spike[1]), integer(spike[2]) }, "\t"))
		end
	end
	local text = table.concat(rows, "\n") .. "\n"
	assert(#text <= 65536, "payload limit")
	return buffer.fromstring(text)
end

function Codec.records(side, name, run, payload)
	assert(side == "SERVER" or side == "CLIENT", "invalid side")
	token(name)
	token(run)
	local text = buffer.tostring(payload)
	assert(#text > 0 and #text <= 65536, "payload limit")
	local checked = side .. "|" .. name .. "|" .. run .. "\0" .. text
	local a, b = 1, 0
	for i = 1, #checked do
		a = (a + string.byte(checked, i)) % 65521
		b = (b + a) % 65521
	end
	local checksum = string.format("%08x", b * 65536 + a)
	local count = math.ceil(#text / 512)
	local records = {}
	for index = 1, count do
		local bytes = {}
		for offset = (index - 1) * 512, math.min(index * 512, #text) - 1 do
			table.insert(bytes, string.format("%02x", buffer.readu8(payload, offset)))
		end
		table.insert(records, table.concat({ side, name, "BUF", "1", run, tostring(index), tostring(count), tostring(#text), checksum, table.concat(bytes) }, "|"))
	end
	return records
end

return Codec
