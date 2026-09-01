--!optimize 2
--!strict

-- 04/20/26
-- @t003z
-- perf: O(1) Get/Release via free-stack

-- Types
export type PoolObject<T> = {
	Object: T
}
type InternalObject<T> = {
	Object: T,
	Busy: boolean,
	Time: number
}
export type Pool<T> = {
	Get: (self: Pool<T>, Force: boolean?) -> T?,
	Release: (self: Pool<T>, Object: T) -> (),
	Destroy: (self: Pool<T>) -> ()
}
export type InternalPool<T> = Pool<T> & {
	_pool: {InternalObject<T>},
	_lookup: {[T]: InternalObject<T>},
	_free: {InternalObject<T>}
}

-- Module
local InternalModule = {}
InternalModule.__index = InternalModule
local PoolModule = {}

-- Get a object from the pool.
function InternalModule.Get<T>(self: InternalPool<T>, Force: boolean?): T?

	local freeCount = #self._free
	if freeCount > 0 then
		local object = table.remove(self._free, freeCount) :: InternalObject<T>
		object.Busy = true
		object.Time = time()
		return object.Object
	end

	if Force then
		local oldestTime = math.huge
		local oldestObject: InternalObject<T>? = nil
		for _, object in self._pool do
			if object.Time < oldestTime then
				oldestTime = object.Time
				oldestObject = object
			end
		end

		if oldestObject then
			oldestObject.Busy = true
			oldestObject.Time = time()
			return oldestObject.Object
		end
	end

	return nil
end

-- Release a object back into the pool.
function InternalModule.Release<T>(self: InternalPool<T>, Object: T)

	local internal = self._lookup[Object]
	if not internal then return end
	if not internal.Busy then return end
	internal.Busy = false
	internal.Time = 0

	table.insert(self._free, internal);
	(Object :: Instance).Parent = nil

end

-- Destroy the object pool.
function InternalModule.Destroy<T>(self: InternalPool<T>)

	for _, object in self._pool do
		if typeof(object.Object) == "Instance" then
			(object.Object :: Instance):Destroy()
		end
	end

	setmetatable(self, nil)
end

-- Create a new object pool.
function PoolModule.new<T>(Object: T, Fill: number): Pool<T>
	local pool = {} :: {InternalObject<T>}
	local lookup = {} :: {[T]: InternalObject<T>}
	local free = {} :: {InternalObject<T>}

	for _ = 1, Fill do

		local object = (Object :: Instance):Clone()

		local internal = {
			Object = object,
			Busy = false,
			Time = 0
		}

		table.insert(pool, internal)
		lookup[object] = internal
		table.insert(free, internal)
	end

	local self = setmetatable({
		_pool = pool,
		_lookup = lookup,
		_free = free
	}, InternalModule) :: InternalPool<T>
	return self
end

return PoolModule
