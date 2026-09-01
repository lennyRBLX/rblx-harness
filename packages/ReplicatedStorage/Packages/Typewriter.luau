local DEFAULT_SPEED = 0.075

return function(label: TextLabel | TextButton | TextBox, text: string, speed: number?)
	local delay = speed or DEFAULT_SPEED

	label.Text = ""
	for i = 1, #text do
		label.Text = string.sub(text, 1, i)
		task.wait(delay)
	end
end
