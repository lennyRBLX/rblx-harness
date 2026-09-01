local ROBUX_SIGN = "\238\128\130"

local MarketplaceService = game:GetService("MarketplaceService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Commatize = require(ReplicatedStorage.Packages.Commatize)
local Translate = require(ReplicatedStorage.Packages.Translate)
local Retry = require(ReplicatedStorage.Packages.Retry)

return function(label: TextLabel | TextButton | ProximityPrompt | { [number]: TextLabel | TextButton | ProximityPrompt }, format: (sign: string, price: string) -> string, id: number, noCommas: boolean?)
	task.defer(function()
		local success, info = Retry(30, 6, function()
			return MarketplaceService:GetProductInfo(id, Enum.InfoType.Product)
		end)
		
		local text = ""
		if not success then
			text = Translate:FromPlayer("Loading") .. "..."
		elseif type(info) == "table" then
			text = format(ROBUX_SIGN, (noCommas and tostring(info.PriceInRobux)) or Commatize(info.PriceInRobux))
		end
		
		for _, l in pairs(typeof(label) == "table" and label or { label }) do
			if not success or type(info) == "table" then
				local property = "Text"
				if l:IsA("ProximityPrompt") then
					property = "ActionText"
				end
				
				l[property] = text
			end
		end
	end)
end