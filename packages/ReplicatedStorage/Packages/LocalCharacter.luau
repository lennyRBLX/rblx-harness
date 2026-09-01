local Players = game:GetService("Players")
local Player = Players.LocalPlayer

local Character, Humanoid, Root, Head = nil, nil, nil, nil
local Initialized = false

local function characterAdded(character)
	if not character then
		return
	end
	
	Character = character
	Humanoid = nil
	Root = nil
	Head = nil

	-- loop until EVERY part resolves, not just the first: parts replicate / rebuild on separate frames
	-- (an R15 conversion swaps the rig), so Head can appear after Humanoid + Root. `or` not `and` —
	-- with `and` the loop exited the instant ONE part was found, caching the rest nil for this whole life.
	while Character == character and (not Humanoid or not Root or not Head) do
		Humanoid = character:FindFirstChild("Humanoid")
		Root = character:FindFirstChild("HumanoidRootPart")
		Head = character:FindFirstChild("Head")
		task.wait()
	end
end

return function()
	if not Initialized then
		Initialized = true
		
		Player.CharacterAdded:Connect(characterAdded)
		characterAdded(Player.Character)
	end
	
	-- reconcile against the LIVE character every call: re-fetch any ref that is missing or orphaned.
	-- A part can appear or be swapped out after the character first loads (late replication, or an R15
	-- conversion rebuilding the rig), which would otherwise leave a cached ref nil/destroyed for the
	-- whole life. Cached refs are reused cheaply via the Parent == character short-circuit.
	local character = Player.Character
	if character then
		Character = character
		Humanoid = (Humanoid and Humanoid.Parent == character and Humanoid) or character:FindFirstChild("Humanoid")
		Root = (Root and Root.Parent == character and Root) or character:FindFirstChild("HumanoidRootPart")
		Head = (Head and Head.Parent == character and Head) or character:FindFirstChild("Head")
	else
		Character, Humanoid, Root, Head = nil, nil, nil, nil
	end

	return Character, Humanoid, Root, Head
end