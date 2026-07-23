-- mac_shot_boot.lua : Mac Mesen — 부팅→오프닝 자동진행 스크린샷(ROM 무결성/한글 확인).
--   산출: <프로젝트>/tmp/trace/macshot/f<프레임>.png
local ROOT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/macshot/"
os.execute('mkdir -p "' .. ROOT .. '"')
local STOP_FRAME = 5200

local function press(btn, on)
  local ok = pcall(function() emu.setInput(1, { [btn] = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { [btn] = on }) end) end
end

local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  local on = (fr % 70) < 5
  press("start", on); press("a", on)
  if fr >= 1400 and fr <= 5000 and (fr % 100) == 0 then
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then
      local s = io.open(ROOT .. string.format("f%04d.png", fr), "wb")
      if s then s:write(png); s:close() end
    end
  end
  if fr >= STOP_FRAME and not done then done = true; emu.stop(0) end
end, emu.eventType.endFrame)
