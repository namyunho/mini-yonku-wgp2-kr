-- shot_advpoc.lua : ④PoC 실기 검증 — 어드벤처 오프닝 씬(id 0xC0)이 한글로 뜨는지.
--   부팅 → 크레딧 → 타이틀 → Start → 세이브메뉴(처음부터) → 오프닝 어드벤처 로 자동 진행.
--   (1) 디코더 진입 $C0:39D5 훅으로 **어떤 씬 소스가 로드됐는지** 로깅.
--       PoC 는 표 엔트리를 패치해 씬 0xC0 소스를 $C9:B926 으로 재배치했으므로
--       src=$C9:B926 이 찍히면 재배치·표패치가 실기에서 먹힌 것.
--   (2) 주기적으로 스크린샷 → 한글 대사 육안 확인.
-- 산출: tmp/trace/advpoc/  (scene_log.txt, f<프레임>.png)
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/advpoc/"
local STOP_FRAME = 5200

local rows = {}
local seen = {}

emu.addMemoryCallback(function()
  local st = emu.getState()
  local d = st["cpu.d"]
  local function r16(x)
    return emu.read(d + x, emu.memType.snesWorkRam) + emu.read(d + x + 1, emu.memType.snesWorkRam) * 256
  end
  local addr = r16(0x0A)
  local bank = emu.read(d + 0x0C, emu.memType.snesWorkRam)
  local key = string.format("%02X%04X", bank, addr)
  if not seen[key] then
    seen[key] = true
    local mark = ""
    if bank == 0xC9 and addr == 0xB926 then mark = "   <<<< PoC 재배치 씬 0xC0 (한글)" end
    rows[#rows + 1] = string.format("f=%-6d src=$%02X:%04X%s", st["frameCount"], bank, addr, mark)
    local f = io.open(ROOT .. "scene_log.txt", "w")
    if f then
      f:write("# 디코더 $C0:39D5 진입시 씬 소스(고유). PoC: 씬0xC0 -> $C9:B926 재배치.\n")
      for _, s in ipairs(rows) do f:write(s .. "\n") end
      f:close()
    end
  end
end, emu.callbackType.exec, 0xC039D5, 0xC039D5, emu.cpuType.snes, emu.memType.snesMemory)

local function press(btn, on)
  local ok = pcall(function() emu.setInput(1, { [btn] = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { [btn] = on }) end) end
end

local done = false
emu.addEventCallback(function()
  local fr = emu.getState()["frameCount"]
  -- 주기적 start/A 연타로 크레딧·타이틀·메뉴 통과 후 대사 넘김
  local on = (fr % 70) < 5
  press("start", on); press("a", on)
  -- 오프닝 대사 구간을 넓게 캡처
  if fr >= 1400 and fr <= 5000 and (fr % 100) == 0 then
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then
      local s = io.open(ROOT .. string.format("f%04d.png", fr), "wb")
      if s then s:write(png); s:close() end
    end
  end
  if fr >= STOP_FRAME and not done then done = true; emu.stop(0) end
end, emu.eventType.endFrame)
