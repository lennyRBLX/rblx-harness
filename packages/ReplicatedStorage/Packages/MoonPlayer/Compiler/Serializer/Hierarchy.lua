local Resolver = require("../Resolver")
local StaticProps = require("../../StaticProps")

local function parseKeyframes(keyframes, instance)
	local packs = keyframes:QueryDescendants(">Folder")
	local idx = {}
	
	for _, inst in packs do
		table.insert(idx, tonumber(inst.Name))
	end
	
	table.sort(idx)
	
	local frames = {}

	for _, startTime in idx do
		local pack = keyframes[tostring(startTime)]
		local values = pack:FindFirstChild("Values")
		local eases = pack:FindFirstChild("Eases")
		
		local sortedPack = {}
		for _, value in values:GetChildren() do
			table.insert(sortedPack, tonumber(value.Name))
		end
		
		table.sort(sortedPack)
		
		for _, i in sortedPack do
			local frame = values[tostring(i)]
			local frameTime = startTime + i
			local lastFrame = frames[#frames]

			local isStatic = StaticProps[instance.ClassName]
				and StaticProps[instance.ClassName][keyframes.Name]
			
			local diff = frameTime - (lastFrame and lastFrame.startTime or frameTime)
			if diff > 1 and (lastFrame and not lastFrame.static) and not isStatic then
				lastFrame.count = diff
			end

			if eases then
				local ease = eases:FindFirstChild(tostring(i))

				if ease then
					local easeType = ease:FindFirstChild("Type")
					local easeParams = ease:FindFirstChild("Params")
					
					local params = {}

					if easeParams then
						for _, child in easeParams:GetChildren() do
							params[child.Name] = child.Value
						end
					end

					if lastFrame then
						lastFrame.ease = {
							type = easeType.Value,
							params = params,
							target = frame.Value
						}
					end	
				end
			end

			table.insert(frames, {
				startTime = frameTime,
				value = frame.Value,
				static = isStatic,
				count = 1
			})
		end
	end
	
	return frames
end

local function insertMarker(markers, frame, identifier, name, kfMarkers)
	local markerData = markers[frame]
	if not markerData then
		markerData = {}
		markers[frame] = markerData
	end

	if not markerData[identifier] then
		markerData[identifier] = {
			[name] = kfMarkers
		}
	else 
		markerData[identifier] = kfMarkers
	end
end

local function parseKFMarkers(track)
	local kf = track:FindFirstChild("KFMarkers")
	local markers = {}
	
	if kf then
		for _, val in kf:QueryDescendants("StringValue > StringValue#Val") do
			local name = val.Parent.Value
			local val = val.Value 
			
			markers[name] = val
		end
	end

	return markers
end

local function ParseHierarchy(data, save)
	local frameBuffer = {}
	local defaults = {}
	local tree = {}
	
	local markers = {
		start = {},
		finish = {}
	}
	
	for idx, item in data.Items do
		local identifier = item.Identifier
		local itemData = {
			Identifier = identifier
		}
		
		local frame = save:FindFirstChild(idx)
		
		local rig = frame:FindFirstChild("Rig")
		local markerTrack = frame:FindFirstChild("MarkerTrack")

		local realInstance = Resolver.resolveAnimPath(item.Path)
		if not realInstance then
			return error("failed to resolve: " .. table.concat(item.Path.InstanceNames, "."))
		end

		if rig and item.Path.ItemType == "Rig" then
			local jointsHier, findJointSmart = Resolver.resolveJoints(realInstance)
			
			local joints = rig:QueryDescendants(">#_joint")
			local jointData = {}
		
			for _, joint in joints do
				local jointId = joint:GetAttribute("Identifier")
				
				local hier = joint:FindFirstChild("_hier").Value
				local default = joint:FindFirstChild("default")
				local keyframes = joint:FindFirstChild("_keyframes")

				if default then
					default = default.Value
					
					defaults[tostring(jointId)] = {
						Transform = default
					}
				end
				
				if keyframes then
					local jointData = jointsHier[hier] or (findJointSmart and findJointSmart(hier)) or nil
					if not jointData or not jointData.Joint then
						return error(`failed to resolve: {hier}`)
					end
					
					local isMotor6D = jointData.Joint:IsA("Motor6D")
					for _, keyframe in parseKeyframes(keyframes, realInstance) do
						local frameData = frameBuffer[tostring(keyframe.startTime)]
						if not frameData then
							frameData = {}
							frameBuffer[tostring(keyframe.startTime)] = frameData
						end
						
						if isMotor6D then
							keyframe.value = keyframe.value:Inverse() * default

							if keyframe.ease then
								keyframe.ease.target = keyframe.ease.target:Inverse() * default
							end
						end
						
						frameData[tostring(jointId)] = {
							{
								props = {
									Transform = {
										value = keyframe.value,
										ease = keyframe.ease,
									}
								},
								
								propCount = 1,
								count = keyframe.count	
							}
						}
					end
				end
				
				jointData[tostring(jointId)] = {
					hier = hier,
					default = default
				}
			end
			
			itemData.JointCount = #joints
			itemData.Joints = jointData
		else 
			for _, child in frame:QueryDescendants(">Folder:not(#MarkerTrack)") do
				local default = child:FindFirstChild("default")
				if default then
					local instDefaults = defaults[tostring(identifier)]
					if not instDefaults then
						instDefaults = {}
						defaults[tostring(identifier)] = instDefaults
					end
					
					instDefaults[child.Name] = default.Value
				end
				
				for _, keyframe in parseKeyframes(child, realInstance) do
					local frameData = frameBuffer[tostring(keyframe.startTime)]
					if not frameData then
						frameData = {}
						frameBuffer[tostring(keyframe.startTime)] = frameData
					end
					
					local existingFrameData = frameData[tostring(identifier)]
					if not existingFrameData then
						existingFrameData = {}
						frameData[tostring(identifier)] = existingFrameData
					end
					
					local prop = {
						props = {
							[child.Name] = {
								value = keyframe.value,
								ease = keyframe.ease,
							}
						},

						propCount = 1,
						count = keyframe.count	
					}
					
					table.insert(existingFrameData, prop)
				end
				
			end
		end
		
		if markerTrack then
			for _, track in markerTrack:GetChildren() do
				local startFrame = assert(tonumber(track.Name))
				local width = assert(track:FindFirstChild("width")).Value
				local name = assert(track:FindFirstChild("name")).Value
				local kfMarkers = parseKFMarkers(track)

				insertMarker(markers.start, startFrame, identifier, name, kfMarkers)
				
				if width > 0 then
					local finishFrame = math.min(startFrame + width, data.Information.Length)

					insertMarker(markers.finish, finishFrame, identifier, name, kfMarkers)
				end
			end
		end
		
		tree[tostring(identifier)] = itemData
	end
	
	return {
		markers = markers,
		defaults = defaults,
		frameBuffer = frameBuffer,
		tree = tree
	}
end

return ParseHierarchy
