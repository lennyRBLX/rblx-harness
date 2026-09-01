--!native

local getNewTransform = function(transform: CFrame, fromJoint: Motor6D, toJoint: Motor6D, fromRoot: BasePart, toRoot: BasePart, fromLimb: BasePart, toLimb: BasePart, fromRigRoot: BasePart, toRigRoot: BasePart)
	local fromOffset = fromRigRoot.CFrame:ToObjectSpace(fromLimb.CFrame)
	local toOffset = toRigRoot.CFrame:ToObjectSpace(toLimb.CFrame)
	
	--When fromRig and toRig are stacked on top of eachother, `finalCFrame` is the CFrame value of the toLimb if it was stacked on top of the fromLimb during the current keyframe, relative to the fromRoot
	local finalCFrame = (fromJoint.C0 * (fromJoint.C1 * transform):Inverse()) * fromOffset:ToObjectSpace(toOffset)
	
	--finalCFrame is relative to the fromRoot, it needs to be relative to the toRoot
	local toRootOffset = fromRigRoot.CFrame:ToObjectSpace(fromRoot.CFrame):ToObjectSpace(toRigRoot.CFrame:ToObjectSpace(toRoot.CFrame))
	
	--Given the final cframe of a Part1, and the c0 and c1 of the Motor6D, you can find the transform property 
	return toJoint.C1:Inverse() * finalCFrame:Inverse() * toRootOffset * toJoint.C0
end

local getRigsData = function(fromName: string, fromRig: Model, toRig: Model, converter: table)
	local toName = converter[fromName]
	if toName then
		local fromLimb = fromRig:FindFirstChild(fromName)
		local toLimb = toRig:FindFirstChild(toName)
		if fromLimb and toLimb then
			local fromJoint, toJoint
			for _, v in fromRig:GetDescendants() do
				if v:IsA("Motor6D") and v.Part1 == fromLimb then
					fromJoint = v
					break
				end
			end
			for _, v in toRig:GetDescendants() do
				if v:IsA("Motor6D") and v.Part1 == toLimb then
					toJoint = v
					break
				end
			end
			if fromJoint and toJoint then
				local fromRoot, toRoot = fromJoint.Part0, toJoint.Part0
				if fromRoot and toRoot then
					local fromRigRoot
					local fromRigRootJoint = fromJoint
					while true do
						local currentRoot = fromRigRootJoint.Part0
						if not currentRoot then
							return
						end
						local finished = true
						for _, v in fromRig:GetDescendants() do
							if v:IsA("Motor6D") and v.Part1 == currentRoot then
								fromRigRootJoint = v
								finished = false
								break
							end
						end
						if finished then
							fromRigRoot = fromRigRootJoint.Part0 --Usually just the HumanoidRootPart
							break
						end
					end
					
					local toRigRoot
					local toRigRootJoint = toJoint
					while true do
						local currentRoot = toRigRootJoint.Part0
						if not currentRoot then
							return
						end
						local finished = true
						for _, v in toRig:GetDescendants() do
							if v:IsA("Motor6D") and v.Part1 == currentRoot then
								toRigRootJoint = v
								finished = false
								break
							end
						end
						if finished then
							toRigRoot = toRigRootJoint.Part0 
							break
						end
					end
					
					if fromRigRoot and toRigRoot then
						return fromJoint, toJoint, fromRoot, toRoot, fromLimb, toLimb, fromRigRoot, toRigRoot
					end
				end
			end
		end
	end
end

local getJoint = function(name0: string, name1: string, rig: Model)
	for _, v in rig:GetDescendants() do
		if v:IsA("Motor6D") and v.Part1.Name == name1 and (if name0 then v.Part0.Name == name0 else true) then
			return v
		end
	end
	return false
end

local keyframeSequenceIterator
keyframeSequenceIterator = function(item: KeyframeSequence, fromRig: Model, toRig: Model, converter: table, merge: boolean?, lastRoot: BasePart?)
	local fromName = item.Name
	if item:IsA("Pose") then
		local parentPose = item.Parent
		local toName = converter[fromName]
		local fromJoint, toJoint, fromRoot, toRoot, fromLimb, toLimb, fromRigRoot, toRigRoot = getRigsData(fromName, fromRig, toRig, converter)
		local motor6d = getJoint(lastRoot, fromName, fromRig)
		
		local keyframe = item:FindFirstAncestorWhichIsA("Keyframe")

		if merge and motor6d then
			local clone = item:Clone()

			clone:ClearAllChildren()

			local kfMerge = merge[keyframe]
			if not kfMerge then
				kfMerge = {}
				merge[keyframe] = kfMerge
			end

			kfMerge[motor6d] = clone
		end
		
		if fromJoint and motor6d and toName then
			item.Parent = nil
			item.Name = toName

			local currentPose = item
			while true do
				local currentRootName
				for _, v in toRig:GetDescendants() do
					if v:IsA("Motor6D") and v.Part1.Name == currentPose.Name then
						currentRootName = v.Part0.Name
						break
					end
				end

				if not currentRootName then
					warn(parentPose:GetFullName() .. "." .. fromName)
					warn(converter[currentPose.Name])
					currentPose.Parent = parentPose
					break
				end

				local shouldBreak = false
				for _, v in keyframe:GetDescendants() do
					if v:IsA("Pose") and v.Name == currentRootName then
						currentPose.Parent = v
						shouldBreak = true
						break
					end
				end
				if shouldBreak then
					break
				end

				if currentRootName == "HumanoidRootPart" then
					currentPose.Parent = keyframe
					break
				end


				local newPose = Instance.new("Pose")
				newPose.Weight = 1
				newPose.Name = currentRootName
				
				newPose:SetAttribute("AutoGenerated", true)

				currentPose.Parent = newPose
				currentPose = newPose
			end

			item.CFrame = getNewTransform(item.CFrame, fromJoint, toJoint, fromRoot, toRoot, fromLimb, toLimb, fromRigRoot, toRigRoot)
		end
	end

	for _, v in item:GetChildren() do
		keyframeSequenceIterator(v, fromRig, toRig, converter, merge, if item:IsA("Pose") then fromName else lastRoot)
	end
end

local keyframeSequenceConvert = function(sequence: KeyframeSequence, fromRig: Model, toRig: Model, converter: table, populateUnusedJoints: boolean?, merge: boolean?)
	local mergeTable = merge and {}
	keyframeSequenceIterator(sequence, fromRig, toRig, converter, mergeTable)
	
	if mergeTable then
		for keyframe, kfMerge in mergeTable do
			for motor6d, pose in kfMerge do
				pose.Parent = keyframe
			end
			for motor6d, pose in kfMerge do
				local parentName = motor6d.Part0.Name

				for _, parent in kfMerge do
					if parent.Name == parentName then
						pose.Parent = parent
						break
					end
				end

				if pose.Parent == keyframe then
					local parentPose = keyframe:FindFirstChild(parentName, true)

					if parentPose then
						pose.Parent = parentPose
					end
				end
			end
		end
	end
	
	for _, v in sequence:GetDescendants() do
		if v:IsA("Pose") and v:GetAttribute("AutoGenerated") then
			if v.CFrame == CFrame.identity then
				local shouldDestroy = true
				for _, v2 in v:GetDescendants() do
					if not (v2:IsA("Pose") and v2:GetAttribute("AutoGenerated") and v2.CFrame == CFrame.identity) then
						shouldDestroy = false
						break
					end
				end
				if shouldDestroy then
					v.Parent = nil --Parenting to nil, not destroying, because I don't want to work with Instance:Destroy's garbage collector behavior. No memory leak.
				end
				continue
			end
			v:SetAttribute("AutoGenerated", nil)
		end
	end
	
	if populateUnusedJoints then
		local basePose = Instance.new("Pose")
		basePose:SetAttribute("AutoGenerated", true)

		local fromJoints = {}
		for _, v in fromRig:GetDescendants() do
			if v:IsA("Motor6D") then
				local part1 = v.Part1
				if part1 and part1:IsDescendantOf(fromRig) then
					fromJoints[part1.Name] = v
				end
			end
		end

		local newJoints = {}
		for _, v in toRig:GetDescendants() do
			if v:IsA("Motor6D") then
				local part1 = v.Part1
				if part1 and part1:IsDescendantOf(toRig) then
					newJoints[part1.Name] = v
				end
			end
		end

		for i, _ in fromJoints do
			local toName = converter[i]
			if toName then
				newJoints[toName] = nil
			end
		end

		for _, v in sequence:GetChildren() do
			if v:IsA("Keyframe") then
				local newJoints = table.clone(newJoints)
				while true do
					local shouldBreak = true
					for i2, v2 in newJoints do
						if v:FindFirstChild(i2, true) then
							newJoints[i2] = nil
							continue
						end
						local part0 = v2.Part0
						if part0 then
							local parentName = part0.Name
							local parentPose = v:FindFirstChild(parentName, true)
							if parentPose then
								local pose = basePose:Clone()
								pose.Name = i2
								pose.Parent = parentPose

								newJoints[i2] = nil
								shouldBreak = false
							end
						end
					end
					if shouldBreak then
						break
					end
				end
			end
		end
	end
end

local curveAnimationIterator
curveAnimationIterator = function(item: Instance, fromRig: Model, toRig: Model, converter: table, merge: boolean?, lastRoot: BasePart?)
	local fromName = item.Name
	if item:IsA("Folder") then
		local parent = item.Parent
		local toName = converter[fromName]
		local fromJoint, toJoint, fromRoot, toRoot, fromLimb, toLimb, fromRigRoot, toRigRoot = getRigsData(fromName, fromRig, toRig, converter)
		local motor6d = getJoint(lastRoot, fromName, fromRig)
		
		local animRoot = item:FindFirstAncestorWhichIsA("CurveAnimation")

		if merge and motor6d then
			local clone = item:Clone()

			for _, v in clone:GetChildren() do
				if v:IsA("Folder") then
					v:Destroy()
				end
			end

			merge[motor6d] = clone
		end
		
		if fromJoint and motor6d and toName then
			item.Parent = nil
			item.Name = toName
			
			local currentPose = item
			while true do
				local currentRootName
				for _, v in toRig:GetDescendants() do
					if v:IsA("Motor6D") and v.Part1.Name == currentPose.Name then
						currentRootName = v.Part0.Name
						break
					end
				end

				if not currentRootName then
					warn(parent:GetFullName() .. "." .. fromName)
					warn(converter[currentPose.Name])
					currentPose.Parent = parent
					break
				end

				local shouldBreak = false
				for _, v in animRoot:GetDescendants() do
					if v:IsA("Folder") and v.Name == currentRootName then
						currentPose.Parent = v
						shouldBreak = true
						break
					end
				end
				if shouldBreak then
					break
				end

				if currentRootName == "HumanoidRootPart" then
					currentPose.Parent = animRoot
					break
				end


				local newPose = Instance.new("Folder")
				newPose.Name = currentRootName

				currentPose.Parent = newPose
				currentPose = newPose
			end
			
			local rotationCurve = item:FindFirstChild("Rotation")
			local positionCurve = item:FindFirstChild("Position")
			
			if rotationCurve or positionCurve then
				if not rotationCurve then
					rotationCurve = Instance.new("EulerRotationCurve")
					rotationCurve.Name = "Rotation"
					rotationCurve.Parent = item
				end
				if not positionCurve then
					positionCurve = Instance.new("Vector3Curve")
					positionCurve.Name = "Position"
					positionCurve.Parent = item
				end
				
				local isEuler = rotationCurve:IsA("EulerRotationCurve")
				local isQuaternion = rotationCurve:IsA("RotationCurve") --It's not actually quaternion math, some Roblox staff member just lied about it and there's no documentation. It's just matrices represented by CFrame
				local isPosition = positionCurve:IsA("Vector3Curve")
				
				if isPosition and (isEuler or isQuaternion) then
					local fromPositionCurve = positionCurve:Clone()
					local fromRotationCurve = rotationCurve:Clone()
					
					local positions = {}
					
					if isEuler then
						local fromCurves = {fromRotationCurve:X(), fromRotationCurve:Y(), fromRotationCurve:Z()}
						local floatCurves = {rotationCurve:X(), rotationCurve:Y(), rotationCurve:Z()}
						for i = 1, #fromCurves do
							local curve = fromCurves[i]
							local keys = curve:GetKeys()
							for i2 = 1, #keys do
								local key = keys[i2]
								
								local transform = fromRotationCurve:GetRotationAtTime(key.Time) + Vector3.new(unpack(fromPositionCurve:GetValueAtTime(key.Time), 1, 3))
								local newTransform = getNewTransform(transform, fromJoint, toJoint, fromRoot, toRoot, fromLimb, toLimb, fromRigRoot, toRigRoot)
								
								local rotation = newTransform.Rotation
								local position = newTransform.Position
								
								for i3 = 1, #floatCurves do
									local realCurve: FloatCurve = floatCurves[i3]
									local newValue = select(i3, rotation:ToEulerAngles(rotationCurve.RotationOrder))
									key.Value = newValue
									realCurve:InsertKey(key)
								end
								
								positions[key.Time] = position
							end
						end
					else
						local fromCurve = rotationCurve:Clone()
						local keys = fromCurve:GetKeys()
						
						for i = 1, #keys do
							local key = keys[i]
							
							local transform = (fromCurve:GetValueAtTime(key.Time) or CFrame.identity) + Vector3.new(unpack(fromPositionCurve:GetValueAtTime(key.Time), 1, 3))
							local newTransform = getNewTransform(transform, fromJoint, toJoint, fromRoot, toRoot, fromLimb, toLimb, fromRigRoot, toRigRoot)
							
							local rotation = newTransform.Rotation
							local position = newTransform.Position
							
							key.Value = rotation
							rotationCurve:InsertKey(key)
							
							positions[key.Time] = position
						end
					end
					
					local fromCurves = {fromPositionCurve:X(), fromPositionCurve:Y(), fromPositionCurve:Z()}
					local floatCurves = {positionCurve:X(), positionCurve:Y(), positionCurve:Z()}
					
					local axes = {"X", "Y", "Z"}
					
					for i = 1, #fromCurves do
						local curve = fromCurves[i]
						local keys = curve:GetKeys()
						for i2 = 1, #keys do
							local key = keys[i2]
							
							local transform = CFrame.new(unpack(fromPositionCurve:GetValueAtTime(key.Time), 1, 3))
							local newTransform = getNewTransform(transform, fromJoint, toJoint, fromRoot, toRoot, fromLimb, toLimb, fromRigRoot, toRigRoot)
							
							local position = newTransform.Position
							
							for i3 = 1, #floatCurves do
								local idiot: FloatCurve = floatCurves[i3]
								key.Value = position[axes[i3]]
								idiot:InsertKey(key)
							end
						end
					end
					
					for t, offset in positions do
						for i = 1, #floatCurves do
							local fromCurve = fromCurves[i]
							local curve = floatCurves[i]

							local axisOffset = offset[axes[i]]
							if axisOffset ~= 0 then
								curve:InsertKey(FloatCurveKey.new(t, axisOffset, Enum.KeyInterpolationMode.Linear))
							end
						end
					end
				else
					warn(`Could not convert {item:GetFullName()}. Unknown curve data types`)
				end
			end
		end
	end
	
	for _, v in item:GetChildren() do
		curveAnimationIterator(v, fromRig, toRig, converter, merge, if item:IsA("Folder") then fromName else lastRoot)
	end
end

local curveAnimationConvert
curveAnimationConvert = function(curveAnimation: CurveAnimation, fromRig: Model, toRig: Model, converter: table, populateUnusedJoints: boolean?, merge: boolean?)
	local mergeTable = merge and {}
	curveAnimationIterator(curveAnimation, fromRig, toRig, converter, mergeTable)
	
	if mergeTable then
		for motor6d, pose in mergeTable do
			pose.Parent = curveAnimation
		end
		for motor6d, pose in mergeTable do
			local parentName = motor6d.Part0.Name
			
			for _, parent in mergeTable do
				if parent.Name == parentName then
					pose.Parent = parent
					break
				end
			end
			
			if pose.Parent == curveAnimation then
				local parentPose = curveAnimation:FindFirstChild(parentName, true)

				if parentPose then
					pose.Parent = parentPose
				end
			end
		end
	end
	
	if populateUnusedJoints then
		local basePose = Instance.new("Folder")
		Instance.new("EulerRotationCurve", basePose).Name = "Rotation" --Intentional parenting order
		Instance.new("Vector3Curve", basePose).Name = "Position"
		
		basePose:SetAttribute("AutoGenerated", true)
		
		local fromJoints = {}
		for _, v in fromRig:GetDescendants() do
			if v:IsA("Motor6D") then
				local part1 = v.Part1
				if part1 and part1:IsDescendantOf(fromRig) then
					fromJoints[part1.Name] = v
				end
			end
		end
		
		local newJoints = {}
		for _, v in toRig:GetDescendants() do
			if v:IsA("Motor6D") then
				local part1 = v.Part1
				if part1 and part1:IsDescendantOf(toRig) then
					local name = part1.Name
					if not curveAnimation:FindFirstChild(name, true) then
						newJoints[name] = v
					end
				end
			end
		end
		
		for i, _ in fromJoints do
			local toName = converter[i]
			if toName then
				newJoints[toName] = nil
			end
		end
		
		while true do
			local shouldBreak = true
			for i, v in newJoints do
				local part0 = v.Part0
				if part0 then
					local parentName = part0.Name
					local parentPose = curveAnimation:FindFirstChild(parentName, true)
					if parentPose then
						local pose = basePose:Clone()
						pose.Name = i
						pose.Parent = parentPose
						
						newJoints[i] = nil
						shouldBreak = false
					end
				end
			end
			if shouldBreak then
				break
			end
		end
	end
	
	for _, v in curveAnimation:GetDescendants() do
		if v:IsA("Folder") then
			if not (v:FindFirstChild("Position", true) or v:FindFirstChild("Rotation", true)) then
				v.Parent = nil
			end
		end
	end
end


return function(clip: AnimationClip, fromRig: Model, toRig: Model, converter: table, populateUnusedJoints: boolean?, merge: boolean?)
	if clip:IsA("KeyframeSequence") then
		return keyframeSequenceConvert(clip, fromRig, toRig, converter, populateUnusedJoints, merge)
	elseif clip:IsA("CurveAnimation") then
		return curveAnimationConvert(clip, fromRig, toRig, converter, populateUnusedJoints, merge)
	end
end