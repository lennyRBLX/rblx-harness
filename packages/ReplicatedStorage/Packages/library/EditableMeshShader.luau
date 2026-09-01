local AssetService = game:GetService("AssetService")
local RunService = game:GetService("RunService")

local module = {}
module.__index = module

function module.new(Mesh: MeshPart, VertexCallback: () -> Vector3, FragmentCallback: () -> Vector2, SpeedValue: NumberValue?)
	local NewMesh = {}
	setmetatable(NewMesh, module)
	
	NewMesh.Mesh = Mesh
	task.spawn(function()
		local result, errorMsg = pcall(function()
			print(NewMesh.Name)
			NewMesh.EditableMesh = AssetService:CreateEditableMeshAsync(Mesh.MeshContent)
		end)
		if not result then print(errorMsg) return end

		local UpdateMesh = AssetService:CreateMeshPartAsync(Content.fromObject(NewMesh.EditableMesh))
		NewMesh.Mesh:ApplyMesh(UpdateMesh)

		NewMesh.Vertices = NewMesh.EditableMesh:GetVertices()
		NewMesh.UVs = NewMesh.EditableMesh:GetUVs()
		NewMesh.VerticesPositions = {}
		NewMesh.UVPositions = {}
		NewMesh.FixedTime = 0
		NewMesh.Time = 0

		for _, VertexId in NewMesh.Vertices do
			local Position = NewMesh.EditableMesh:GetPosition(VertexId)
			NewMesh.VerticesPositions[VertexId] = Position
		end

		for _, UvId in NewMesh.UVs do
			local UVPosition = NewMesh.EditableMesh:GetUV(UvId)
			NewMesh.UVPositions[UvId] = UVPosition
		end

		NewMesh.Update = RunService.PreRender:Connect(function(dt)
			NewMesh.FixedTime += dt
			if SpeedValue then
				NewMesh.Time += dt * SpeedValue.Value
			else
				NewMesh.Time = NewMesh.FixedTime
			end

			for VertexId, VertexPosition in NewMesh.VerticesPositions do
				NewMesh.EditableMesh:SetPosition(VertexId, VertexCallback(VertexPosition, NewMesh.Time, dt, NewMesh.FixedTime))
			end

			for UvId, UvPosition in NewMesh.UVPositions do
				NewMesh.EditableMesh:SetUV(UvId, FragmentCallback(UvPosition, NewMesh.Time, dt, NewMesh.FixedTime))
			end
		end)
	end)
	
	return NewMesh
end

function module:Destroy()
	self.Update:Disconnect()
	self.EditableMesh:Destroy()
end

return module
