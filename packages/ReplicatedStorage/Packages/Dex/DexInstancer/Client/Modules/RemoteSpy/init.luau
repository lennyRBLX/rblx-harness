--[[
	Script Viewer App Module
	
	A script viewer that is basically a notepad
]]

-- Common Locals
local Main,Lib,Apps,Settings -- Main Containers
local Explorer, Properties, RemoteSpy, Notebook -- Major Apps
local API,RMD,env,service,plr,create,createSimple -- Main Locals
local HolderFrame,RemoteList,CallsList,CurrentFrame -- Ui Locals

local remotes = {}
local remotesObject = {}
local player = game:GetService("Players").LocalPlayer
local serializer = require(script.Serializer)

--remotes = {
--	remoteFrame = {
--		remote = game.ReplicatedStorage.exemple,
--  		icon  = 75,
--		logs = {
--			[1] = {
--				workspace,
--				"exemple string",
--				69
--			}
--		}
--	}
--}

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
	RemoteSpy = Apps.RemoteSpy
	Notebook = Apps.Notebook
end

local function addLogFrame(args, remoteTable, index)
	-- Add a log frame to the remote --
	local args = remoteTable.logs[index]
	local template = CallsList.Template.TemplateFrame:Clone()
		
	local finalString = `( {serializer(args, 1)} )`

	template.Parent = CallsList
	template.Visible = true
	template.Top.Icon.ImageRectOffset = Vector2.new(16 * remoteTable.icon)
	template.Top.RemoteName.Text = remoteTable.remote:GetFullName()
	template.Calls.args.Text = finalString
end

local function addLog(remoteFrame, args, show)
	table.insert(remotes[remoteFrame].logs, args)

	if show then
		addLogFrame(remotes[remoteFrame], #remotes[remoteFrame].logs)
	end
end

local function clearLogs(remoteFrame)
	-- Clear the logs for the specific remote --

	if not remoteFrame then return end

	remotes[remoteFrame].logs = {}

	for i,v in CallsList:GetChildren() do
		if v:IsA("Frame") then
			v:Destroy()
		end
	end
end

local function showLogs(remoteFrame, show)
	-- Show the log list for a specific remote --

	for i,v in CallsList:GetChildren() do
		if v:IsA("Frame") then
			v:Destroy()
		end
	end

	for i,v in remotes[remoteFrame].logs do
		-- Add Remotes logged back
		addLogFrame(v, remotes[remoteFrame], i)
	end
end

local function addRemote(name, remoteType, remoteCaptured)
	local template = remotesObject[remoteCaptured]

	if not template then
		template = RemoteList.Template.TemplateFrame:Clone()
		remotesObject[remoteCaptured] = template

		local iconId

		if remoteType == "RemoteEvent" or remoteType == "UnreliableRemoteEvent" then
			iconId = 75
		else
			iconId = 74
		end

		remotes[template] = {
			remote = remoteCaptured,
			icon = iconId,
			logs = {}
		}

		template.Icon.ImageRectOffset = Vector2.new(16*iconId, 0)
		template.Visible = true
		template.Parent = RemoteList
		template.RemoteName.Text = name

		template.Click.MouseButton1Click:Connect(function()
			showLogs(template, true)
			CurrentFrame = template
		end)
	end

	return template
end

local function main()
	local RemoteSpy = {}

	local window

	RemoteSpy.Init = function()
		window = Lib.Window.new()
		window:SetTitle("Remote Spy")
		window:Resize(735, 395)
		RemoteSpy.Window = window

		--ScrollBar = Lib.ScrollBar.new()
		--ScrollBar.Gui.Position = UDim2.new(0,0,0,0)
		--ScrollBar.Gui.Parent = window.GuiElems.Content
		local HolderFrame = script.Holder:Clone()
		RemoteList = HolderFrame.Left.RemotesList
		CallsList = HolderFrame.Right.CallListHold.CallsList

		HolderFrame.Parent = window.GuiElems.Content

		local clearButton = Lib.Button.new()
		clearButton.Parent = HolderFrame.Right.CallListHold.CallsList
		clearButton.Size = UDim2.new(0.9, 0,0, 20)
		clearButton.Text = "Clear Logs"
		clearButton.Name = "ClearButton"

		clearButton.MouseButton1Click:Connect(function()
			clearLogs(CurrentFrame)
		end)

		player:FindFirstChildOfClass("PlayerGui").DexInstancer.remotes.ReplicateArguments.OnClientEvent:Connect(function(playerFired, remote, ...)
			if remote then
				local remoteFrame = addRemote(remote.Name, remote.ClassName, remote)
				addLog(remoteFrame, {...}, false)
			end
		end)

		--task.delay(3, function()
		--	local exempleRemote = game.ReplicatedStorage.exemple
		--	addRemote(exempleRemote.Name, "RemoteEvent", exempleRemote)
		--end)
	end

	return RemoteSpy
end

-- TODO: Remove when open source
if gethsfuncs then
	_G.moduleData = {InitDeps = initDeps, InitAfterMain = initAfterMain, Main = main}
else
	return {InitDeps = initDeps, InitAfterMain = initAfterMain, Main = main}
end