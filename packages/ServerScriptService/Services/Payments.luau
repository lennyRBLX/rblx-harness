--[[
Payments:
	Wraps Products, DevProducts, Gamepasses, and all marketplace logic
	[R DES2]. The receipt contract is ruled, not prose:

	DATA21 — grants in ProcessReceipt only: handlers mutate Profile.Data
	only, PurchaseId & grant save as 1 unit, PurchaseGranted only after the
	id is in LastSavedData, NotProcessedYet only before any grant. The one
	exception is the dead-profile hold exit: that grant either died unsaved
	with the session or rides the final save into the rejoin retry
	unfinalized — goods and payment converge either way.

	DATA36 — a cached PurchaseId retry returns PurchaseGranted & re-runs no
	handlers; the cache is an idempotency ledger, evicted only past its
	recorded bound. Any finite bound leaves a re-grant window past it for a
	failed-to-record PurchaseGranted — recorded rather than closed.

	GIFTS — receiptInfo carries no recipient and a receipt handler reaches
	the buyer's profile only, so Gift() records { ProductId, To, At } in
	Payments.Pending before the prompt, and the receipt handler pops the
	newest entry matching its ProductId: PlayerData:Send(To, "Gift",
	{ Uid, Kind, Id, Amount, From }) first, removal only after the send
	lands. The Uid is the receipt's PurchaseId — the send precedes the
	grant-save, so a retry after a failed save re-sends the same Uid and
	dedupe is the recipient's job. No pending match returns false: never
	route blind; a later retry resolves it or the purchase refunds
	unprocessed. The project owns OnMessage("Gift", ...) and the block it
	writes — the handler appends and nothing else (processed() precedes it;
	a throw drops the message for good), drops any Uid already recorded,
	caps the set oldest-first like Purchases, and applies afterward: "pass"
	through GrantGamepass, "entitlement" idempotently, "money" once per Uid
	— money is additive and a duplicate doubles it. Residual: two
	same-product gifts that both die unsaved can swap recipients on retry;
	payloads are per-product, so only "money" doubles — recorded rather
	than closed.

	Concurrency (documented: the same purchase may run on two servers at
	once) is safe through ProfileStore's single-session guarantee — a grant
	persists only through the session holder.

	VERIFY BEFORE PUBLISH: Store-tab test mode first, then a real dev
	product on a live place — buy once; force a retry (rejoin mid-hold);
	confirm exactly one grant, PurchaseGranted on the retry, and the receipt
	status moving Open -> Closed. create_boilerplate --test LIVE.Payments
	emits the logging shim. A gift adds: buy through Gift() once, force the
	same retry, confirm exactly one Gift append at the recipient.
]]

local INFO_NAME = "Passes"
local PURCHASE_CACHE_MAX = 1000
local PENDING_MAX = 100
local SAVE_RETRY_SECONDS = 30

local GIFT_KINDS = { pass = true, entitlement = true, money = true }

local ServerScriptService = game:GetService("ServerScriptService")
local MarketplaceService = game:GetService("MarketplaceService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Players = game:GetService("Players")

local EntityCleanup = require(ReplicatedStorage.Packages.EntityCleanup)
local Exclusive = require(ServerScriptService.Modules.Exclusive)
local Signal = require(ReplicatedStorage.Packages.Signal)

local PlayerData = require(ServerScriptService.Services.PlayerData)
local PlayerDataTyped = require(ServerScriptService.Services.PlayerData.Typed)

local m = {
	Setup = false,

	PlayerOwns = {},
	Products = {},
	ValidIDs = {},

	PurchaseCallbacks = {},
	Gifts = {},

	Owns = Signal.new(),
}

-- privates
local giftBusy = {}

local function cleanupPlayer(player)
	m.PlayerOwns[player] = nil
	giftBusy[player] = nil
end

local function iterPageItems(pages)
	return coroutine.wrap(function()
		local pagenum = 1
		while true do
			for _, item in pages:GetCurrentPage() do
				coroutine.yield(item, pagenum)
			end
			if pages.IsFinished then
				break
			end

			pages:AdvanceToNextPageAsync()
			pagenum += 1
		end
	end)
end

function m:updatePlayerReplicatedInfo(player)
	local cache = self.PlayerOwns[player]
	if not cache then
		return
	end

	Exclusive:Set(player, INFO_NAME, cache)
end

local function purchaseCached(profile, purchaseId)
	for _, id in profile.Data.Payments.Purchases do
		if id == purchaseId then
			return true
		end
	end

	return false
end

local function cachePurchase(profile, purchaseId)
	-- the id and the grant land in Profile.Data together; bounded,
	-- oldest-first eviction — an evicted id was already confirmed saved
	table.insert(profile.Data.Payments.Purchases, purchaseId)
	while #profile.Data.Payments.Purchases > PURCHASE_CACHE_MAX do
		table.remove(profile.Data.Payments.Purchases, 1)
	end
end

local function savedPurchase(profile, purchaseId)
	local saved = profile.LastSavedData
	if typeof(saved) ~= "table" or typeof(saved.Payments) ~= "table" or typeof(saved.Payments.Purchases) ~= "table" then
		return false
	end

	for _, id in saved.Payments.Purchases do
		if id == purchaseId then
			return true
		end
	end

	return false
end

local function holdForSave(profile, purchaseId)
	-- hold until the id appears in LastSavedData, waiting on OnAfterSave and
	-- re-forcing Save(). No clock timeout — the callback may yield
	-- indefinitely (documented), and holding is what makes the finalize
	-- imply a durable grant. Only a dead profile ends the hold.
	if savedPurchase(profile, purchaseId) then
		return true
	end

	local done = false
	local connection = profile.OnAfterSave:Connect(function()
		if savedPurchase(profile, purchaseId) then
			done = true
		end
	end)

	local lastForce = 0
	while not done and profile:IsActive() do
		if os.clock() - lastForce >= SAVE_RETRY_SECONDS or lastForce == 0 then
			lastForce = os.clock()
			profile:Save()
		end
		task.wait(0.2)
	end

	-- the result records even after the player leaves: give the session's
	-- final save a short grace to confirm, so a departure mid-hold still
	-- resolves instead of leaving the purchase unresolved
	local grace = os.clock() + 5
	while not done and os.clock() < grace do
		if savedPurchase(profile, purchaseId) then
			done = true
		end
		task.wait(0.2)
	end

	connection:Disconnect()
	return done or savedPurchase(profile, purchaseId)
end

local function giftReceipt(player, receiptInfo)
	-- deref the definition before the lock: a missing one (unreachable —
	-- GiftProduct pairs it with this handler) throws without holding it
	local gift = m.Gifts[receiptInfo.ProductId]
	local kind, itemId, amount = gift.Kind, gift.Id, gift.Amount
	local productId = tostring(receiptInfo.ProductId)

	-- one pop+send per buyer at a time: a second same-product receipt
	-- searching while this one yields in Send would pop against a shifted
	-- queue and cross recipients
	while giftBusy[player] do
		task.wait()
	end

	if not PlayerData:Valid(player) then
		return false
	end

	giftBusy[player] = true

	local pending = PlayerDataTyped.Payments(player).Pending
	local index = nil
	for i = #pending, 1, -1 do
		-- newest first: a cancelled prompt strands its entry, and the latest
		-- Gift call is the intent this receipt pays for
		if pending[i].ProductId == productId then
			index = i
			break
		end
	end

	if not index then
		giftBusy[player] = nil
		return false
	end

	-- send before removal: the Uid is the PurchaseId, so a retry that
	-- re-runs a sent-but-unsaved receipt re-sends the same Uid and the
	-- recipient's dedupe absorbs it; removal and the purchase cache then
	-- save as 1 unit [DATA21]
	local sent = PlayerData:Send(pending[index].To, "Gift", {
		Uid = receiptInfo.PurchaseId,
		Kind = kind,
		Id = itemId,
		Amount = amount,
		From = player.UserId,
	})

	if not sent then
		giftBusy[player] = nil
		return false
	end

	table.remove(pending, index)
	giftBusy[player] = nil
	return true
end

local function processReceipt(receiptInfo)
	local player = Players:GetPlayerByUserId(receiptInfo.PlayerId)
	if not player then
		-- the player left: nothing is granted and nothing is cached — they
		-- hold escrow, the purchase stays unresolved, and Roblox retries it
		-- on their next join. The retry IS the offline queue [R DATA21].
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	if not PlayerData:Valid(player) then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	local profile = PlayerData:Profile(player)
	if not profile or not profile:IsActive() then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	local purchaseId = receiptInfo.PurchaseId

	-- a retry of an already-granted receipt never re-runs the handlers
	if not purchaseCached(profile, purchaseId) then
		-- every guard that can refuse runs BEFORE the grant: past this point
		-- the only exits are a confirmed save or a dead profile
		local handlers = m.PurchaseCallbacks[receiptInfo.ProductId]
		if handlers then
			for _, handler in handlers do
				local success, result = pcall(handler, player, receiptInfo)
				if not success then
					warn("Payments.processReceipt | " .. player.Name .. " | " .. tostring(result))
					return Enum.ProductPurchaseDecision.NotProcessedYet
				elseif result == false then
					return Enum.ProductPurchaseDecision.NotProcessedYet
				end
			end
		end

		cachePurchase(profile, purchaseId)
		m:OwnsGamepass(player, receiptInfo.ProductId)
		m:updatePlayerReplicatedInfo(player)
	end

	-- grant only after the mutation is committed [DATA21]: hold, never time
	-- out — a dead profile is the only other exit, and its final save
	-- carries the grant into the rejoin retry unfinalized
	if not holdForSave(profile, purchaseId) then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	return Enum.ProductPurchaseDecision.PurchaseGranted
end

-- functions
function m:GetProducts()
	local result = self.Products or {}
	if #result > 0 then
		return result
	end

	for product in iterPageItems(MarketplaceService:GetDeveloperProductsAsync()) do
		result[#result + 1] = product
	end

	self.Products = result
	return result
end

function m:GetProduct(name)
	local products = self:GetProducts()
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

	local products = self:GetProducts()
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

	local cache = self.PlayerOwns[player]
	if not cache and PlayerData then
		local payData = PlayerData:Valid(player) and PlayerDataTyped.Payments(player)
		if payData then
			cache = payData.Owns
			self.PlayerOwns[player] = cache
			EntityCleanup:Add(player, cleanupPlayer, nil, "Payments.cleanupPlayer")
		end
	end

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
	if cache and result then
		self.Owns:Fire(player, id)
		cache[tostring(id)] = true
	end

	return result
end

function m:GrantGamepass(player, id)
	-- the grant IS the Owns entry [additive, never cleared]: Roblox has no
	-- server-side gamepass grant, so a gifted pass exists only here and
	-- OwnsGamepass honors it without a marketplace call
	assert(typeof(player) == "Instance" and player:IsA("Player"), "Payments.GrantGamepass | player must be an instance and a player")
	assert(typeof(id) == "number", "Payments.GrantGamepass | id must be a number")

	self:OwnsGamepass(player, 0) -- lazy-inits the cache without a marketplace call
	local cache = self.PlayerOwns[player]
	if not cache then
		return false
	end

	local key = tostring(id)
	if cache[key] then
		return true
	end

	cache[key] = true
	self.Owns:Fire(player, id)
	self:updatePlayerReplicatedInfo(player)
	return true
end

function m:OnPurchase(id, callback)
	if not self.PurchaseCallbacks[id] then
		self.PurchaseCallbacks[id] = {}
	end

	local callbacks = self.PurchaseCallbacks[id]
	callbacks[#callbacks + 1] = callback
end

function m:RemoveOnPurchase(id, callback)
	local callbacks = self.PurchaseCallbacks[id]
	if callbacks then
		local index = table.find(callbacks, callback)
		if index then
			table.remove(callbacks, index)
		end
	end
end

function m:GiftProduct(productId, gift)
	-- boot-time on every server: a retry can land where Gift() never ran,
	-- and the payload must be a pure function of the ProductId — Pending
	-- carries the recipient only
	assert(typeof(productId) == "number", "Payments.GiftProduct | productId must be a number")
	assert(typeof(gift) == "table", "Payments.GiftProduct | gift must be a table")
	assert(GIFT_KINDS[gift.Kind], "Payments.GiftProduct | Kind must be \"pass\", \"entitlement\" or \"money\"")
	if gift.Kind == "money" then
		assert(typeof(gift.Amount) == "number", "Payments.GiftProduct | money gifts need a numeric Amount")
	elseif gift.Kind == "pass" then
		assert(typeof(gift.Id) == "number", "Payments.GiftProduct | pass gifts need a numeric gamepass Id")
	else
		assert(gift.Id ~= nil, "Payments.GiftProduct | entitlement gifts need an Id")
	end
	assert(self.Gifts[productId] == nil, "Payments.GiftProduct | duplicate definition for " .. productId)

	self.Gifts[productId] = gift
	self:OnPurchase(productId, giftReceipt)
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

function m:Gift(player, productId, recipientUserId)
	assert(typeof(player) == "Instance" and player:IsA("Player"), "Payments.Gift | player must be an instance and a player")
	assert(typeof(productId) == "number", "Payments.Gift | productId must be a number")
	assert(typeof(recipientUserId) == "number", "Payments.Gift | recipientUserId must be a number")
	assert(self.Gifts[productId], "Payments.Gift | no GiftProduct definition for " .. productId)

	if not PlayerData:Valid(player) then
		return false
	end

	local payData = PlayerDataTyped.Payments(player)

	-- the entry precedes the prompt: the receipt may land before
	-- PromptProductPurchase even returns
	table.insert(payData.Pending, {
		ProductId = tostring(productId),
		To = recipientUserId,
		At = os.time(),
	})

	-- bounded like Purchases: cancelled prompts strand entries, and
	-- evicting oldest-first drops strays or turns a live receipt into a
	-- no-match refund — never a wrong send
	while #payData.Pending > PENDING_MAX do
		table.remove(payData.Pending, 1)
	end

	return (self:PromptPurchase(player, productId))
end

function m:SetupPlayer(player)
	while not PlayerData:Valid(player) and player:IsDescendantOf(Players) do
		task.wait()
	end

	self:OwnsGamepass(player, 0)
	self:updatePlayerReplicatedInfo(player)
end

function m:Start()
	if self.Setup then
		return self
	end

	self.Setup = true

	for _, player in Players:GetPlayers() do
		task.spawn(self.SetupPlayer, self, player)
	end

	MarketplaceService.ProcessReceipt = processReceipt

	return self
end

-- events

return m
