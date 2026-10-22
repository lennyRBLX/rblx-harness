-- Payments owns marketplace calls and profile-backed receipt grants.
-- Each product has one atomic Profile.Data grant callback. Its mutation and
-- purchase ID share the same profile save. Acknowledgement waits for that ID in
-- LastSavedData. Replay protection ends when the bounded ledger evicts the ID.

const INFO_NAME = "Passes"
const PURCHASE_CACHE_MAX = 1000
const CLEANUP_PLAYER = "Payments.Player"
const DEFAULT_STATE = { Initialized = false }

const ServerScriptService = game:GetService("ServerScriptService")
const MarketplaceService = game:GetService("MarketplaceService")
const ReplicatedStorage = game:GetService("ReplicatedStorage")
const RunService = game:GetService("RunService")
const Players = game:GetService("Players")

const EntityCleanup = require(ReplicatedStorage.Packages.EntityCleanup)
const Exclusive = require(ServerScriptService.Modules.Exclusive)
const TableUtil = require(ReplicatedStorage.Packages.TableUtil)
const Signal = require(ReplicatedStorage.Packages.Signal)

const PlayerData = require(ServerScriptService.Services.PlayerData)

const PaymentsTypes = require(ReplicatedStorage.Types.Payments)

const ProcessingPurchases = {}

const m = {
	__players = {},
	
	Products = {},
	ValidIDs = {},

	PurchaseCallbacks = {},

	Owns = Signal.new()
}

-- privates
const function getPlayerData(player)
	return if m:GetState(player) and PlayerData:Valid(player) then PlayerData:Get(player, script.Name) else nil
end

const function cleanupPlayer(player, arguments)
	const state = arguments[1]
	if m:GetState(player) ~= state then
		return
	end

	m.__players[player] = nil
end

const function containsPurchase(purchases, purchaseId)
	for _, id in purchases do
		if id == purchaseId then
			return true
		end
	end

	return false
end

function m:updatePlayerReplicatedInfo(player)
	const data = getPlayerData(player)
	const cache = data and data.Owns
	if not cache then
		return
	end

	Exclusive:Set(player, INFO_NAME, cache)
end

function m:grantReceipt(receiptInfo)
	const player = Players:GetPlayerByUserId(receiptInfo.PlayerId)
	if not player or not PlayerData:Valid(player) then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	-- a retry of an already-granted receipt never re-runs the handlers
	const data, purchaseId = getPlayerData(player), receiptInfo.PurchaseId
	if not containsPurchase(data.Purchases, purchaseId) then
		-- Handlers mutate live profile data. A handler must not partially grant
		-- before returning false or raising an error.
		const handlers = self.PurchaseCallbacks[receiptInfo.ProductId]
		const handler = handlers and handlers[1]

		if not handlers or #handlers ~= 1 or type(handler) ~= "function" then
			return Enum.ProductPurchaseDecision.NotProcessedYet
		end

		const success, result = pcall(handler, player, receiptInfo)
		if not success then
			warn("Payments.processReceipt | " .. player.Name .. " | " .. tostring(result))
			return Enum.ProductPurchaseDecision.NotProcessedYet
		elseif not result then
			return Enum.ProductPurchaseDecision.NotProcessedYet
		end

		table.insert(data.Purchases, purchaseId)
		while #data.Purchases > PURCHASE_CACHE_MAX do
			table.remove(data.Purchases, 1)
		end

		self:OwnsGamepass(player, receiptInfo.ProductId)
		self:updatePlayerReplicatedInfo(player)
	end

	-- grant only after the mutation is committed [DATA21]: hold, never time
	-- out — a dead profile is the only other exit, and its final save
	-- carries the grant into the rejoin retry unfinalized

	if not PlayerData:AwaitSave(player, script.Name, function(saved)
		return typeof(saved.Purchases) == "table" and containsPurchase(saved.Purchases, purchaseId)
	end) then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	return Enum.ProductPurchaseDecision.PurchaseGranted
end

const function processReceipt(receiptInfo)
	const purchaseId = receiptInfo.PurchaseId
	if ProcessingPurchases[purchaseId] then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	ProcessingPurchases[purchaseId] = true

	const ok, decision = pcall(m.grantReceipt, m, receiptInfo)
	ProcessingPurchases[purchaseId] = nil

	if not ok then
		warn(`Payments.processReceipt | {tostring(decision)}`)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	return decision
end

function m:playerAdded(player)
	if player.Parent ~= Players then
		return
	end

	local state = self:GetState(player)
	if not state then
		state = TableUtil.Copy(DEFAULT_STATE, true)
		self.__players[player] = state

		EntityCleanup:Add(player, cleanupPlayer, { state }, CLEANUP_PLAYER)
	end

	if not getPlayerData(player) then
		return
	end

	if not state.Initialized then
		state.Initialized = true
		self:OwnsGamepass(player, 0)
	end

	self:updatePlayerReplicatedInfo(player)
end

-- functions
function m:GetState(player: Player): PaymentsTypes.RuntimeState?
	return self.__players[player]
end

function m:GetProducts()
	const result = self.Products or {}
	if #result > 0 then
		return result
	end

	const success, products = pcall(function()
		const pages = MarketplaceService:GetDeveloperProductsAsync()
		const fetched = {}

		while true do
			for _, product in pages:GetCurrentPage() do
				fetched[#fetched + 1] = product
			end

			if pages.IsFinished then
				return fetched
			end

			pages:AdvanceToNextPageAsync()
		end
	end)

	if not success then
		warn("Payments.GetProducts | " .. tostring(products))
		return result
	end

	self.Products = products
	return products
end

function m:GetProduct(name)
	const products = self:GetProducts()
	for _, product in products do
		if product.Name == name then
			return product
		end
	end

	return nil
end

function m:ValidProduct(id)
	if self.ValidIDs[id] then
		return true
	end

	const products = self:GetProducts()
	for _, product in products do
		if product.ProductId == id then
			self.ValidIDs[id] = true
			return true
		end
	end

	return false
end

function m:OwnsGamepass(player, id)
	assert(typeof(player) == "Instance" and player:IsA("Player"), "Payments.OwnsGamepass | player must be an instance and a player")
	assert(typeof(id) == "number", "Payments.OwnsGamepass | id must be a number")

	const state, data = self:GetState(player), getPlayerData(player)
	const cache = data and data.Owns

	if cache and cache[tostring(id)] then
		return true
	end

	local success, result = RunService:IsStudio(), RunService:IsStudio()
	if player.UserId < 0 then
		success, result = false, nil
	end

	if not success and id ~= 0 then
		success, result = pcall(MarketplaceService.UserOwnsGamePassAsync, MarketplaceService, player.UserId, id)
	end

	if not success then
		return false
	end

	-- removing unowned gamepasses would cause gifts to be deleted
	const live = getPlayerData(player)
	if cache and result and self:GetState(player) == state and live and live.Owns == cache and player.Parent == Players then
		self.Owns:Fire(player, id)
		cache[tostring(id)] = true
	end

	return result
end

function m:OnPurchase(id, callback)
	assert(type(callback) == "function", "Payments.OnPurchase | callback must be a function")

	const callbacks = self.PurchaseCallbacks[id]
	assert(not callbacks or #callbacks == 0 or (#callbacks == 1 and callbacks[1] == callback), "Payments.OnPurchase | each product requires one atomic grant callback")

	if callbacks and callbacks[1] == callback then
		return
	end

	self.PurchaseCallbacks[id] = { callback }
end

function m:RemoveOnPurchase(id, callback)
	const callbacks = self.PurchaseCallbacks[id]
	if callbacks then
		const index = table.find(callbacks, callback)
		if index then
			table.remove(callbacks, index)
		end
	end
end

function m:PromptPurchase(player, id)
	if not id then
		return false
	elseif self:ValidProduct(id) then
		return pcall(MarketplaceService.PromptProductPurchase, MarketplaceService, player, id)
	else
		return pcall(MarketplaceService.PromptGamePassPurchase, MarketplaceService, player, id)
	end
end

function m:Start()
	for _, player in Players:GetPlayers() do
		task.spawn(self.playerAdded, self, player)
	end

	Players.PlayerAdded:Connect(function(player)
		self:playerAdded(player)
	end)

	MarketplaceService.ProcessReceipt = processReceipt
end

return m
