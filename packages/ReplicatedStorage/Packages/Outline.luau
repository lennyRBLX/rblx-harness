local Highlight = Instance.new("Highlight")
Highlight.FillTransparency = 1
Highlight.DepthMode = Enum.HighlightDepthMode.Occluded
Highlight.Name = "Outline"
Highlight.Parent = workspace.Terrain

return function(new: Model | BasePart, value: boolean?)
	if Highlight.Adornee == new and not value then
		Highlight.Adornee = nil
	else
		Highlight.Adornee = new
	end
end