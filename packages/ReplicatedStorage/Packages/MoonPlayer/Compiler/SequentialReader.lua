local Stream = require("./Stream")


local Reader = {}

function Reader.new(deserializer)
	local frameBuffer = Stream.new(
		deserializer.frameBuffer:tobuffer()
	)
	
	local self = setmetatable({
		currentFrame = -1,
		sequence = table.clone(deserializer.sequence),
		deserializer = deserializer,
		
		frameBuffer = frameBuffer,
		
	}, { __index = Reader })
	
	
	return self
end

function Reader:processNextFrame()
	local stream = self.frameBuffer 
	local nextFrame = stream:readu16()
	
	if nextFrame ~= self.currentFrame then
		stream.read -= 2 
		warn("expected frame", self.currentFrame, "got", nextFrame)
		
		return
	end
	
	local frame = {}
	for _ = 1, stream:readu16() do
		local instanceId = stream:readu16()
		local props = {}
		
		for _ = 1, stream:readu16() do
			local propList = {
				duration = stream:readu16(),
				props = {}
			}
			
			for _ = 1, stream:readu8() do
				local name = assert(self.deserializer.strings[stream:readu16()])
				local value, cfid = self.deserializer:deserializeValue(stream)
				
				local prop = {
					name = name,
					value = value
				}
				
				if stream:readbool() then
					local easeType = assert(self.deserializer.strings[stream:readu16()])
					local target = self.deserializer:deserializeValue(stream)
					
					local params = {}
					for _ = 1, stream:readu8() do
						local key = assert(self.deserializer.strings[stream:readu16()])
						local value = self.deserializer:deserializeValue(stream) 
						
						params[key] = value
					end
					
					prop.ease = {
						type = easeType,
						target = target,
						params = params 
					}
				end
				
				table.insert(propList.props, prop)
			end
			
			table.insert(props, propList)
		end
		
		frame[tostring(instanceId)] = props
	end
	
	return frame
end

function Reader:requestFrame()
	if #self.sequence == 0 then
		return
	end
	
	self.currentFrame += 1

	local nextFrame = self.sequence[1]
	if nextFrame == self.currentFrame then
		table.remove(self.sequence, 1)
		
		return self:processNextFrame()
	end

	return
end

return Reader