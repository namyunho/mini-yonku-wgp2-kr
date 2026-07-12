-- shot_adv.lua : poc_shot 경로로 초상화 조언상자 장면까지 진행 후 스크린샷.
-- 출력 파일명에 ROM 이름을 넣어 12/13/14 advance 비교가 가능.
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/adv/"
local SHOTS = { [1150] = true, [1180] = true, [1205] = true }
local STOP_FRAME = 1210

local tag = "rom"
do
  local ok, info = pcall(function() return emu.getRomInfo() end)
  if ok and info and info.name then
    tag = info.name:gsub("%.smc$", ""):gsub("[^%w_]", "_")
  end
end

local function pressStart(on)
  local ok = pcall(function() emu.setInput(1, { start = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { start = on }) end) end
end

local done = false
local function onFrame()
  local fr = emu.getState()["frameCount"]
  local on = (fr >= 200 and fr < 208) or (fr >= 400 and fr < 408) or (fr >= 600 and fr < 608)
  pressStart(on)
  if SHOTS[fr] then
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then
      local s = io.open(ROOT .. tag .. "_" .. fr .. ".png", "wb")
      if s then s:write(png); s:close() end
    end
  end
  if fr >= STOP_FRAME and not done then
    done = true
    emu.stop(0)
  end
end
emu.addEventCallback(onFrame, emu.eventType.endFrame)
