return function(start)
	for _, mode in { "cleanup", "no-module", "no-packages" } do
		local removed
		local started, cleaned = 0, 0
		const player = {}
		const cleanupModule, serviceModule = {}, {}
		const cleanup = {
			Cleanup = function(self, entity)
				assert(entity == player, "cleanup received a different player")
				cleaned += 1
			end
		}
		const service = {
			Start = function(self)
				assert(mode ~= "cleanup" or removed, "service started before cleanup was connected")
				started += 1
			end
		}
		serviceModule.IsA = function(self, name)
			return name == "ModuleScript"
		end
		const server = {
			Services = {
				GetChildren = function()
					return { serviceModule }
				end
			},
			FindFirstChild = function()
				return nil
			end
		}
		const packages = {
			FindFirstChild = function(self, name)
				return if mode == "cleanup" and name == "EntityCleanup" then cleanupModule else nil
			end
		}
		const services = {
			ServerScriptService = server,
			ReplicatedStorage = {
				FindFirstChild = function(self, name)
					return if mode ~= "no-packages" and name == "Packages" then packages else nil
				end
			},
			Players = {
				PlayerRemoving = {
					Connect = function(self, callback)
						assert(not removed, "duplicate cleanup connection")
						removed = callback
					end
				}
			}
		}
		start({
			GetService = function(self, name)
				return assert(services[name], "unexpected service")
			end
		}, function(module)
			return if module == cleanupModule then cleanup else service
		end, {
			spawn = function(callback)
				callback()
			end
		})
		assert(started == 1 and cleaned == 0, "startup changed service execution or cleaned early")
		if mode == "cleanup" then
			removed(player)
			assert(cleaned == 1, "departure did not dispatch cleanup")
		else
			assert(not removed, "cleanup connected without its package")
		end
	end
	print("S01 pass")
end
