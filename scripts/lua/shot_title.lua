-- shot_title.lua : 크레딧 이후 타이틀(로고) 화면을 포착. 스타트 1회로 크레딧 넘긴 뒤
--   여러 프레임 스크린샷 → 로고 화면 확인. 산출 tmp/trace/title/title_<fr>.png
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/title/"
local STOP = 900
local function pressStart(on)
  local ok = pcall(function() emu.setInput(1, { start = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { start = on }) end) end
end
local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  -- 크레딧(~f360) 이후 한 번만 스타트로 넘김
  pressStart(fr >= 430 and fr < 438)
  if fr >= 360 and fr % 40 == 0 then
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then
      local s = io.open(ROOT .. "title_" .. fr .. ".png", "wb"); if s then s:write(png); s:close() end
    end
  end
  if fr >= STOP and not done then done = true; emu.stop(0) end
end, emu.eventType.endFrame)
