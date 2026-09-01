local Compiler = require("@self/Compiler")
local Player = require("@self/Player")
local Types = require("@self/Types")

local MoonPlayer = {
	Compiler = Compiler,
	Player = Player
}

return MoonPlayer :: Types.MoonPlayer