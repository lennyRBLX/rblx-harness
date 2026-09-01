-- validates the deny_scan entry table: parses, and every entry names a live
-- rule id with the six fields. Run under `lute run`; session-gate check #3
-- and the wrapper both call it.
local table_ = require("./deny_table")

local FIELDS = { "id", "pattern", "paths", "except", "presence", "message" }
local count = 0
for id, entry in table_ do
	assert(typeof(entry) == "table", id .. ": entry is not a table")
	assert(entry.id == id, id .. ": id field mismatch")
	for _, f in FIELDS do
		assert(entry[f] ~= nil, id .. ": missing field " .. f)
	end
	count += 1
end
print("ok " .. count)
