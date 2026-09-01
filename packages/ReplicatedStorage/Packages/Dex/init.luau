local explorer = {}
local plrs = game:GetService("Players")

explorer.start = function(plrInfo)
	local plr
	if typeof(plrInfo) == "string" then 
		plr = plrs:FindFirstChild(plrInfo)
	elseif typeof(plrInfo) == "number" then
		plr = plrs:GetPlayerByUserId(plrInfo)
	elseif typeof(plrInfo) == "Instance" then
		if plrInfo.ClassName == "Player" then
			plr = plrInfo
		end
	end

	if not plr then return warn("[EXPLORER] COULD NOT FIND PLAYER: ", string.upper(tostring(plrInfo))) end

	local playerUi = plr:FindFirstChild("PlayerGui")
	if not playerUi then return warn("[EXPLORER] COULD NOT FIND PLAYERGUI FOR: ", string.upper(tostring(plrInfo))) end

	local ui = script.DexInstancer:Clone()
	ui.Parent = playerUi
end

return explorer