--[[
Theme:
	The Backrooms terminal design system — single source of truth for the palette / font / corner radius /
	overlay tweens shared across the Gui controllers (Shop, Classes, Skins, Settings, Titles, PartyHUD,
	GroupReward, MatchmakingHUD). Edit a shared theme value once, here, instead of in ~8 hand-synced copies.

	Controllers re-bind the keys they use (`local COLOR_BG = Theme.COLOR_BG`) so usage sites stay unchanged.
	File-UNIQUE colours (tab tints, fail/success swatches, slider bg, hover/ready states) stay local to their
	controller — only genuinely shared keys live here. Two values intentionally diverge and stay local
	overrides: GroupReward's CORNER_RADIUS (5, not 3) and Titles' brighter COLOR_OWNED.
]]

local Theme = {}

-- palette
Theme.COLOR_BG = Color3.fromRGB(12, 11, 9)
Theme.COLOR_PANEL = Color3.fromRGB(20, 19, 15)
Theme.COLOR_PANEL_INNER = Color3.fromRGB(16, 15, 12)
Theme.COLOR_ACCENT = Color3.fromRGB(170, 160, 80)
Theme.COLOR_ACCENT_DIM = Color3.fromRGB(100, 95, 50)
Theme.COLOR_TEXT = Color3.fromRGB(190, 185, 165)
Theme.COLOR_DIM = Color3.fromRGB(80, 75, 60)
Theme.COLOR_SCANLINE = Color3.fromRGB(170, 160, 80)
Theme.COLOR_SELECTED_BG = Color3.fromRGB(30, 28, 18)
Theme.COLOR_LOCKED = Color3.fromRGB(60, 55, 45)
Theme.COLOR_OWNED = Color3.fromRGB(60, 120, 50) -- shop/menu "owned" green (Titles overrides with a brighter tag green)

-- type
Theme.FONT = Enum.Font.Code
Theme.FONT_HEADER = Enum.Font.RobotoMono
Theme.CORNER_RADIUS = UDim.new(0, 3) -- GroupReward overrides locally to UDim.new(0, 5)

-- overlay tweens
Theme.TWEEN_OPEN = TweenInfo.new(0.3, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
Theme.TWEEN_CLOSE = TweenInfo.new(0.2, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
Theme.TWEEN_CAMERA = TweenInfo.new(0.5, Enum.EasingStyle.Quart, Enum.EasingDirection.Out)

return Theme
