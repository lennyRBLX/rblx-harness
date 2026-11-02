local PatchCore = {}

local function CheckExport(Export)
	assert(type(Export) == "table", "Module must return a table")
	assert(not table.isfrozen(Export), "Frozen exports need a project-specific adapter")
	assert(getmetatable(Export) == nil, "Metatable exports need a project-specific adapter")

	for Key, Value in Export do
		assert(type(Key) == "string", "Only named exports are supported")
		local ValueType = typeof(Value)
		assert(ValueType ~= "number" or Value == Value, "NaN exports cannot be compared for undo")
		assert(
			ValueType == "function"
				or ValueType == "string"
				or ValueType == "number"
				or ValueType == "boolean"
				or ValueType == "Vector2"
				or ValueType == "Vector3"
				or ValueType == "CFrame"
				or ValueType == "Color3"
				or ValueType == "EnumItem"
				or ValueType == "UDim"
				or ValueType == "UDim2"
				or ValueType == "NumberRange",
			"Export " .. Key .. " has unsupported type " .. ValueType .. "; use an adapter"
		)
	end
end

function PatchCore.Snapshot(Export)
	CheckExport(Export)
	return table.clone(Export)
end

function PatchCore.Matches(Export, Snapshot)
	for Key, Value in Export do
		if Snapshot[Key] ~= Value then
			return false
		end
	end

	for Key, Value in Snapshot do
		if Export[Key] ~= Value then
			return false
		end
	end

	return true
end

function PatchCore.Replace(Export, Replacement, Expected)
	CheckExport(Export)
	CheckExport(Replacement)

	if Expected then
		assert(
			PatchCore.Matches(Export, Expected),
			"Exports changed since the last reload; refusing overwrite"
		)
	end

	local Before = table.clone(Export)
	local After = table.clone(Replacement)

	for Key in Export do
		Export[Key] = nil
	end

	for Key, Value in After do
		Export[Key] = Value
	end

	return Before, After
end

return PatchCore
