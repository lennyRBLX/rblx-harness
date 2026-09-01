local module = {}


module.EFP = game.Workspace
local BoatTween = require(script.BoatTween)
local TS =game:GetService("TweenService")


module.ProcessPart = function(Args)
	local Maid = Args.Maid
	local FX = Args.FX
	local Part = Args.Part
	local Debri = Args.Debri or 10
	
	local Clone = Maid:give(FX:Clone())
	for i,v in pairs(Clone:GetChildren())do
		Maid:give(v)
		game.Debris:AddItem(v,Debri)
		v.Parent = Part
	end
end

module.PlayTween = function(Object,Info,CompletedFunction)
	local Tween = BoatTween:Create(Object,Info)
	Tween:Play()

	local ok = Tween.Completed:Once(function()
		if CompletedFunction then
			CompletedFunction()
		end
		Tween:Destroy()
	end)
	task.delay(Info.Time, function()
		ok:Disconnect()
		Tween:Destroy()
	end)
end

module.Maid = require(script.Maid)

module.Bezier = require(script.Bezier)

module.Impact = function(CC)
	local CCC = CC:Clone()
	CCC.Parent = game.Lighting
	delay(0.1,function()
		CCC:Destroy()
	end)
end


module.ChangeParticleColor = function(Params)
	local instance = Params.Particle
	local Color = Params.Color
	local Position = Params.Position or Params.Pos

	local Particles = {}
	if instance:IsA("ParticleEmitter") then
		table.insert(Particles,instance)
	else
		for i,v in pairs(instance:GetDescendants())do
			if v:IsA("ParticleEmitter") then
				table.insert(Particles,v)
			end
		end
	end


	for _,Particle in pairs(Particles) do
		if Color then
			local colorKeypoints = {
				ColorSequenceKeypoint.new( 0, Color),  -- At t=0, White
				ColorSequenceKeypoint.new( 1, Color)   -- At t=1, Red
			}
			Particle.Color = ColorSequence.new(colorKeypoints)


		else
			local downray = Ray.new(Position,Vector3.new(0,-100,0))
			local HitPart = game.Workspace:FindPartOnRayWithWhitelist(downray,{game.Workspace.World})
			if HitPart then
				local colorKeypoints = {
					ColorSequenceKeypoint.new( 0, HitPart.Color),  -- At t=0, White
					ColorSequenceKeypoint.new( 1, HitPart.Color)   -- At t=1, Red
				}
				Particle.Color = ColorSequence.new(colorKeypoints)
			end
		end
	end

end

local RayP =RaycastParams.new()
RayP.FilterType = Enum.RaycastFilterType.Include
RayP.FilterDescendantsInstances = {game.Workspace}
module.SetSmoke = function(Args)
	local FX = Args.FX
	local Dist = Args.Dist or 20
	local Anchor = Args.Anchor

	local Results = game.Workspace:Raycast(Anchor.Position,Vector3.new(0,-Dist,0),RayP)
	if Results then
		local colorKeypoints = {
			ColorSequenceKeypoint.new( 0, Results.Instance.Color), 
			ColorSequenceKeypoint.new( 1, Results.Instance.Color)   
		}

		for i,v in pairs(FX:GetDescendants())do
			if v:IsA("ParticleEmitter") then
				v.Color = ColorSequence.new(colorKeypoints)
			end
		end

		return Results
	end
end

module.BindScale = function(Args)
	local FX = Args.FX
	local Maid = Args.Maid
	local Init = Args.Init or 1
	
	local Val = Maid:give(Instance.new("NumberValue"))
	Val.Value = Init
	Val:giveTask(Val.Changed:Connect(function()
		FX:ScaleTo(Val.Value)
	end))
	
	return Val
end

module.Able = function(Args)
	local FX = Args.FX
	local On = Args.On
	
	if On then
		for i,v in pairs(FX:GetDescendants())do
			if v:IsA("ParticleEmitter") then
				v.Enabled = true
			elseif v:IsA("ObjectValue") and v:HasTag("MeshEmitter") then
				v:SetAttribute("Enabled",true)
			end
			
		end
	else
		for i,v in pairs(FX:GetDescendants())do
			if v:IsA("ParticleEmitter") then
				v.Enabled = false
			elseif v:IsA("ObjectValue") and v:HasTag("MeshEmitter") then
				v:SetAttribute("Enabled",false)
			end
		end
	end
end

module.WeldObject = function(...)
	local Object, TargetPart, EffectsTime, DropTime, DestroyTime, ParticleDestroy = ...

	local Obj = Object:Clone()

	local newWeld = Instance.new("Weld")
	newWeld.Parent = TargetPart
	newWeld.Part1 = Obj.PrimaryPart
	newWeld.Part0 = TargetPart

	Obj.Parent = TargetPart.Parent 
	Obj.Name = 'ModuleWelded'

	if EffectsTime then
		for i,v in pairs(Obj:GetDescendants()) do if v:IsA('ParticleEmitter') or v:IsA('Trail')
			then
				task.delay(EffectsTime,function()
					v.Enabled = false
					task.wait(2)
					Obj:Destroy()
				end)
			end
		end

	elseif ParticleDestroy then

		task.delay(DestroyTime,function()

			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('BasePart') then v.Transparency = 1 end end

			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('ParticleEmitter') and v.Enabled == true or v:IsA('Beam') or v:IsA('Texture') or v:IsA('Decal') 
				then v:Destroy() end end

			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('ParticleEmitter') then v:Emit(v:GetAttribute("EmitCount")) end end
			task.wait(3)
			Obj:Destroy()

		end)

	elseif DestroyTime then
		task.delay(DestroyTime,function()
			Obj:Destroy()
		end)

	elseif DropTime then
		task.delay(DropTime,function()
			newWeld:Destroy()
			Obj.Parent = workspace.Effects

			task.wait(0.08)
			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('BasePart') then v.CanCollide = true end end
			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('ParticleEmitter') then v.Enabled = false end end

			task.wait(1.5)
			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('BasePart') then 
					TS:Create(v, TweenInfo.new(0.5, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut), {Transparency = 1}):Play()  
				end 
			end
			task.wait(0.5)
			Obj:Destroy()
		end)

	end

end

module.QuickWeld = function(Args)
	local FX = Args.FX
	local C0 = Args.C0 or CFrame.new(0,0,0)
	local P = Args.P
	local Maid = Args.Maid
	
	FX = FX:Clone()
	local FXWeld = Instance.new("Weld")
	if FX:IsA("Model") then
		FXWeld.Part0 = FX.PrimaryPart 
	else
		FXWeld.Part0 = FX
	end
	FXWeld.Part1 = P
	FXWeld.C0 = C0
	FXWeld.Parent = FX
	FX.Parent = module.EFP
	
	Maid:give(FX)

	return FX,FXWeld
end

module.QuickFX = function(Args)
	local FX = Args.FX
	local Anchor = Args.Anchor
	local Maid = Args.Maid
	local ray = Args.Ray
	
	if ray then
		local Results = game.Workspace:Raycast(Anchor.Position,Vector3.new(0,-10,0),RayP)
		if Results then
			local x,y,z = Anchor:ToOrientation()
			Anchor = CFrame.new(Results.Position) * CFrame.Angles(x,y,z)
		else
			return
		end
	end
	
	FX = FX:Clone()
	if FX:IsA("Model") then
		FX:PivotTo(Anchor)
	elseif FX:IsA("BasePart") then
		
		FX.CFrame = Anchor
	end
	
	if FX:IsA("Attachment") then
		FX.Parent = Anchor
	else
		FX.Parent = module.EFP
	end
	
	
	
	Maid:give(FX)
	
	return FX
end

module.LifeScale = function(Args)
	local FX = Args.FX
	local Scale = Args.Scale

	
	for i,v :ParticleEmitter in pairs(FX:GetDescendants())do
		if v:IsA("ParticleEmitter")  then
			v.Lifetime = NumberRange.new(v.Lifetime.Min * Scale,v.Lifetime.Max * Scale)
		elseif v:IsA("ObjectValue") and v:HasTag("MeshEmitter") then
			local Lifetime = v:GetAttribute("Lifetime")
			v:SetAttribute("Lifetime",NumberRange.new(Lifetime.Min * Scale,Lifetime.Max * Scale))
		end
	end
end

module.dtwait = function(n)
	local dt = 0

	while dt < n do
		dt = dt + game:GetService("RunService").Heartbeat:Wait()
	end

	return dt
end

module.RaiseZIndex= function(Args)
	local FX = Args.FX
	local Count = Args.Count
	
	for i,v in pairs(FX:GetDescendants())do
		if v:IsA("ParticleEmitter") then
			v.ZOffset += Count
		end
	end
end

module.WeldObject = function(...)
	local Object, TargetPart, EffectsTime, DropTime, DestroyTime, ParticleDestroy = ...

	local Obj = Object:Clone()

	local newWeld = Instance.new("Weld")
	newWeld.Parent = TargetPart
	newWeld.Part1 = Obj.PrimaryPart
	newWeld.Part0 = TargetPart

	Obj.Parent = TargetPart.Parent 
	Obj.Name = 'ModuleWelded'

	if EffectsTime then
		for i,v in pairs(Obj:GetDescendants()) do if v:IsA('ParticleEmitter') or v:IsA('Trail')
			then
				task.delay(EffectsTime,function()
					v.Enabled = false
					task.wait(2)
					Obj:Destroy()
				end)
			end
		end
		
    elseif ParticleDestroy then

		task.delay(DestroyTime,function()

			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('BasePart') then v.Transparency = 1 end end

			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('ParticleEmitter') and v.Enabled == true or v:IsA('Beam') or v:IsA('Texture') or v:IsA('Decal') 
				then v:Destroy() end end

			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('ParticleEmitter') then v:Emit(v:GetAttribute("EmitCount")) end end
			task.wait(3)
			Obj:Destroy()

		end)

	elseif DestroyTime then
		task.delay(DestroyTime,function()
			Obj:Destroy()
		end)

	elseif DropTime then
		task.delay(DropTime,function()
			newWeld:Destroy()
			Obj.Parent = workspace.Effects

			task.wait(0.08)
			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('BasePart') then v.CanCollide = true end end
			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('ParticleEmitter') then v.Enabled = false end end

			task.wait(1.5)
			for i,v in pairs(Obj:GetDescendants()) do if v:IsA('BasePart') then 
					TS:Create(v, TweenInfo.new(0.5, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut), {Transparency = 1}):Play()  
				end 
			end
			task.wait(0.5)
			Obj:Destroy()
		end)

	end

end

module.PlayAttachment = function(instance,DebriTime,Params)
	local Part
	if instance:IsA("Part") then
		Part = Part
	elseif instance:IsA("Model") then
		Part = instance.PrimaryPart
	end
	
	
	local HitGround = false
	if Part then
		local Results = game.Workspace:Raycast(Part.Position,Vector3.new(0,-10,0),RayP)
		if Results then
			HitGround = true
		else
			HitGround = false
		end
	end
	
	for i,v in pairs(instance:GetDescendants()) do
		if v:IsA("ParticleEmitter") or v:IsA("ObjectValue") and v:HasTag("MeshEmitter") then
			local Attributes = v:GetAttributes()
			local EmitDelay = Attributes.EmitDelay
			local RepeatCount = Attributes.RepeatCount or 1
			local RepeatDelay = Attributes.RepeatDelay 
			
			task.spawn(function()
				for i = 1,RepeatCount do
					if EmitDelay then
						task.delay(EmitDelay,function()
							if v:IsA("ParticleEmitter") then
								v:Emit(Attributes.EmitCount)
							else
								v:SetAttribute("EMIT",true)
							end
						end)
					else
						if v:IsA("ParticleEmitter") then
							v:Emit(Attributes.EmitCount)
						else
							v:SetAttribute("EMIT",true)
						end					
					end

					--[[]]
					if Attributes.EmitDuration then
						
						if EmitDelay then
							task.delay(EmitDelay,function()
								if v:IsA("ParticleEmitter") then
									v.Enabled= true
								else
									v:SetAttribute("Enabled",true)
								end	
								task.delay(Attributes.EmitDuration,function()
									if v:IsA("ParticleEmitter") then
										v.Enabled= false
									else
										v:SetAttribute("Enabled",false)
									end	
								end)
							end)
						else
							if v:IsA("ParticleEmitter") then
								v.Enabled= true
							else
								v:SetAttribute("Enabled",true)
							end	
							task.delay(Attributes.EmitDuration,function()
								if v:IsA("ParticleEmitter") then
									v.Enabled= false
								else
									v:SetAttribute("Enabled",false)
								end	
							end)
						end
						
						
					end
					if RepeatDelay then
						task.wait(RepeatDelay)
					end
				end
			end)
		

		end

		if v:IsA('PointLight') then
			if DebriTime then
				module.PlayTween(v,{EasingStyle = "Sine",Time = DebriTime,Goal = {Brightness = 0}})
			end
		end

		if v:IsA("Beam") then
			local Attributes = v:GetAttributes()
			local Duration = Attributes.Duration
			local TweenTime = 0.5

			if Params then
				if Params.TweenTime then
					TweenTime = Params.TweenTime
				end
			end

			local function Shut_OFF()
				local ts = game:GetService("TweenService")
				ts:Create(v, TweenInfo.new(TweenTime,Enum.EasingStyle.Sine,Enum.EasingDirection.Out), {Width1 = 0,Width0 = 0}):Play()
			end
			local function Turn_ON()
				local ts = game:GetService("TweenService")
				ts:Create(v, TweenInfo.new(TweenTime,Enum.EasingStyle.Sine,Enum.EasingDirection.Out), {Width1 = Attributes.Width1,Width0 = Attributes.Width0}):Play()
			end

			Turn_ON()

			if Duration then
				task.delay(Duration,function()
					Shut_OFF()
				end)			
			end
		end

	end

	if DebriTime then
		game.Debris:AddItem(instance,DebriTime)
	end
end




module.Yield = function(Args)
	local Time = Args.Time or 5
	local Char = Args.Char
	local Event = Args.Event
	local start = tick()
	while tick() - start < Time do
		local FoundEvent = Char:FindFirstChild(Event)
		if FoundEvent then
			return FoundEvent
		end
		module.dtwait(0.01)
	end
end

module.FastSpawn = require(script.FastSpawn)

module.RandomRot = function()
	return CFrame.Angles(0,math.rad(math.random(-360,360)),0)
end

module.PlayMesh = function(Params)
	task.spawn(function()
		local Model = Params.Model
		local Info = Params.Info or TweenInfo.new(1,Enum.EasingStyle.Sine)
		local Start = Model:FindFirstChild("Start")
		local End = Model:FindFirstChild("End")
		local Stay = Params.Stay
		local Anchor = Params.Anchor
		local EndT = Params.EndT or 1
		local Del = Params.Del
		local Skip = Params.Skip


		
		if Start and End then
			Model.PrimaryPart = Start
			
			if not Skip then
				for i,v in pairs(Model:GetChildren())do
					if v:IsA("BasePart") then
						v.CanCollide = false
						v.Anchored = true
					end
				end
			end
		
			
			if Anchor then Model:SetPrimaryPartCFrame(Anchor) end
			if Params.T then Start.Transparency = Params.T end
			End.Transparency = 1
			Model.Parent = module.EFP

			local Decal = Start:FindFirstChildOfClass("Decal")
			local SpecialMesh = Start:FindFirstChildOfClass("SpecialMesh")
			local SpecialMesh2 = End:FindFirstChildOfClass("SpecialMesh")
			local EndDecal = End:FindFirstChildOfClass("Decal")
			if EndDecal and not Skip then
				EndDecal.Transparency = 1
			end

			local Tween
			if Del then
				local Tween1 = game:GetService("TweenService"):Create(Start,Info,{Size = End.Size,CFrame = End.CFrame})
				Tween1:Play()

				task.delay(Del,function()
					Tween = game:GetService("TweenService"):Create(Start,Info,{Transparency = EndT})
					Tween:Play()

					if Decal then 
						for i,v in pairs(Start:GetChildren())do
							if v:IsA("Decal") then
								game:GetService("TweenService"):Create(v,Info,{Transparency = EndT}):Play()
							end
						end
					end
					
					if SpecialMesh then
						Tween = game:GetService("TweenService"):Create(SpecialMesh,Info,{Scale = SpecialMesh2.Scale}):Play()
					end
				end)

			else

				if SpecialMesh then
					game:GetService("TweenService"):Create(SpecialMesh,Info,{Scale = SpecialMesh2.Scale}):Play()
				end

				if Decal then 
					for i,v in pairs(Start:GetChildren())do
						if v:IsA("Decal") then
							game:GetService("TweenService"):Create(v,Info,{Transparency = EndT}):Play()
						end
					end
					Tween = game:GetService("TweenService"):Create(Start,Info,{Size = End.Size,CFrame = End.CFrame})
					Tween:Play()
				else
					Tween = game:GetService("TweenService"):Create(Start,Info,{Size = End.Size,Transparency = EndT,CFrame = End.CFrame})
					Tween:Play()
				end
				
				
			end

			if not Stay then
				if Del then
					task.wait(Del + 0.1)
				end
				Tween.Completed:Connect(function()
					Model:Destroy()
				end)
			end
		else
			warn("NO START OR END")
		end
	end)
end

module.PlayFlipBook = function(Params)
	local Mesh = Params.Mesh
	local Delta = Params.Delta or 0.02
	local DWC = Params.DWC 
	local Repeat = Params.Repeat or 1
	local FPS = Params.FPS or 1
	local Loop = Params.Loop

	local Folder = Mesh:FindFirstChild("Folder")
	local Decal = Mesh:FindFirstChild("Decal")

	if DWC == nil then
		DWC = true
	end


	if Folder and Decal then
		module.FastSpawn(function()
			for t = 1,Repeat do
				if not Mesh:IsDescendantOf(game.Workspace)then break end
				for i = 1,#Folder:GetChildren(),FPS do
					local FindImage = Folder:FindFirstChild(tostring(i))
					if not FindImage then
						FindImage = Folder:GetChildren()[#Folder:GetChildren()]
					end
					if FindImage then
						Decal.Texture = FindImage.Texture
					end

					if Delta == "Step" then
						game:GetService("RunService").RenderStepped:Wait()
					else
						module.dtwait(Delta)
					end
				end
			end

			
			if DWC and DWC ~= false then
				Mesh:Destroy()
			end
		end)
	end
end

-----
local CameraShaker = require(script.CameraShaker)
local camera = game.Workspace.Camera	 

local function ShakeCamera(shakeCf)
	-- shakeCf: CFrame value that represents the offset to apply for shake effect.
	-- Apply the effect:
	camera.CFrame = camera.CFrame * shakeCf
end
local renderPriority = Enum.RenderPriority.Camera.Value + 1


local camShake = CameraShaker.new(renderPriority, ShakeCamera)

local RunService = game:GetService("RunService")
module.CamShake = function(Preset,Pos,Distance)
	if game:GetService("RunService"):IsClient()  and _G.ServerRunning then
		if Preset == "Stop" then
			CameraShaker:Stop()

		else
			CameraShaker:Stop()

			local CanShake = true
			if Distance then
				local Camera = game.Workspace.CurrentCamera
				local dist = (Camera.CFrame.Position - Pos).Magnitude
				if dist > Distance then
					CanShake = false
				end
			end


			if CanShake then
				camShake:Start()
				camShake:Shake(CameraShaker.Presets[Preset])

				return true
			end
		end
	end

end

module.EditableMeshShader = require(script.EditableMeshShader)

module.GlassLight = function(Parent)
	local Highlight = Instance.new("Highlight")
	Highlight.FillTransparency = 1
	Highlight.OutlineTransparency = 1
	Highlight.Parent = Parent
	
end

return module
