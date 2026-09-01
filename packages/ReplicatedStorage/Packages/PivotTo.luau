local Players = game:GetService("Players")

return function(model: Model, matrix: CFrame, onTop: boolean?)
	onTop = not not onTop

	local root = model:FindFirstChild("HumanoidRootPart")
	local isCharacter = not not Players:GetPlayerFromCharacter(model)
	local pivot = isCharacter and root.CFrame or model:GetPivot()

	if onTop then
		local orientation, size = model:GetBoundingBox()
		matrix *= CFrame.new(0, (pivot.Y - orientation.Y) + size.Y / 2, 0)
	end

	if isCharacter then
		root.CFrame = matrix
		return
	end

	model:PivotTo(matrix)
end