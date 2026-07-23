-- shot_boot.lua : 부팅~타이틀 구간을 주기적으로 스크린샷 → 오프닝 크레딧 화면 포착.
--   산출: tmp/trace/boot_<frame>.png
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/boot/"
local STOP = 720
local function shot(fr)
  local ok, png = pcall(function() return emu.takeScreenshot() end)
  if ok and type(png) == "string" then
    local s = io.open(ROOT .. "boot_" .. fr .. ".png", "wb")
    if s then s:write(png); s:close() end
  end
end
local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  if fr % 60 == 0 then shot(fr) end
  if fr >= STOP and not done then done = true; emu.stop(0) end
end, emu.eventType.endFrame)
