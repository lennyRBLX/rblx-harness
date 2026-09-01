--[[
	Script Viewer App Module
	
	A script viewer that is basically a notepad
]]

-- Common Locals
local Main,Lib,Apps,Settings -- Main Containers
local Explorer, Properties, LocalExec, Notebook -- Major Apps
local API,RMD,env,service,plr,create,createSimple -- Main Locals
local loadstringModule = script.Loadstring
local exec = require(loadstringModule)

local function initDeps(data)
	Main = data.Main
	Lib = data.Lib
	Apps = data.Apps
	Settings = data.Settings

	API = data.API
	RMD = data.RMD
	env = data.env
	service = data.service
	plr = data.plr
	create = data.create
	createSimple = data.createSimple
end

local function initAfterMain()
	Explorer = Apps.Explorer
	Properties = Apps.Properties
	LocalExec = Apps.LocalExec
	Notebook = Apps.Notebook
end

local function main()
	local LocalExec = {}

	local window,codeFrame

	LocalExec.Init = function()
		window = Lib.Window.new()
		window:SetTitle("Local Script")
		window:Resize(500,400)
		LocalExec.Window = window

		codeFrame = Lib.CodeFrame.new()
		codeFrame.Frame.Position = UDim2.fromScale(0, 0)
		codeFrame.Frame.Size = UDim2.fromScale(1, .91)
		codeFrame.Frame.Parent = window.GuiElems.Content

		-- TODO: REMOVE AND MAKE BETTER
		local clear = Instance.new("TextButton",window.GuiElems.Content)
		clear.BackgroundTransparency = 1
		clear.Position = UDim2.fromScale(0, .945)
		clear.Size = UDim2.fromScale(.5, .026)
		clear.Text = "Clear"
		clear.TextColor3 = Color3.new(1, 1, 1)

		clear.MouseButton1Click:Connect(function()
			codeFrame:SetText("")
		end)

		local execute = Instance.new("TextButton",window.GuiElems.Content)
		execute.BackgroundTransparency = 1
		execute.Position = UDim2.fromScale(.5, .945)
		execute.Size = UDim2.fromScale(.5, .026)
		execute.Text = "Execute"
		execute.TextColor3 = Color3.new(1, 1, 1)

		execute.MouseButton1Click:Connect(function()
			local source = codeFrame:GetText()
			
			exec(source)()
		end)
	end

	return LocalExec
end

-- TODO: Remove when open source
if gethsfuncs then
	_G.moduleData = {InitDeps = initDeps, InitAfterMain = initAfterMain, Main = main}
else
	return {InitDeps = initDeps, InitAfterMain = initAfterMain, Main = main}
end