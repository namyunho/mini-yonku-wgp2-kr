-- script_trace.lua : 대사 파서($C1:9554)가 소비하는 뱅크 $C7 스크립트 바이트를 포착.
--   파서는 DBR=$C7로 LDA $0000,Y (+$7EA5E0 카운터)로 스크립트를 1바이트씩 읽는다.
--   → CPU 버스 $C7:0000-FFFF 읽기를 후킹하면 스크립트 위치(addr)와 인코딩 바이트(value)를
--     소비 순서대로 얻는다. 알려진 화면 대사와 대조해 인코딩 모델을 검증한다.
-- 산출: tmp/trace/script_trace.txt (+ script_screen.png)
local ROOT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/"
local GATE_FROM, GATE_TO = 1000, 1205   -- 레이스 대사 타자 구간
local STOP_FRAME = 1205
local MAXLOG = 20000

local log = {}
local n = 0

local function onRead(addr, value)
  local st = emu.getState()
  local fr = st["frameCount"]
  if fr < GATE_FROM or fr > GATE_TO then return end
  n = n + 1
  if n > MAXLOG then return end
  -- addr는 CPU 24비트 버스 주소($C7xxxx). k:pc = 읽은 코드 위치.
  log[#log + 1] = string.format("f=%-5d addr=$%06X val=$%02X pc=$%02X:%04X Y=%04X",
    fr, addr, value, st["cpu.k"], st["cpu.pc"], st["cpu.y"])
end

-- $C7:0000-FFFF CPU 버스 읽기 후킹
emu.addMemoryCallback(onRead, emu.callbackType.read, 0xC70000, 0xC7FFFF,
  emu.cpuType.snes, emu.memType.snesMemory)

local function pressStart(on)
  local ok = pcall(function() emu.setInput(1, { start = on }) end)
  if not ok then pcall(function() emu.setInput(1, 0, { start = on }) end) end
end

local done = false
local function onFrame()
  local fr = emu.getState()["frameCount"]
  local on = (fr >= 200 and fr < 208) or (fr >= 400 and fr < 408) or (fr >= 600 and fr < 608)
  pressStart(on)
  if fr >= STOP_FRAME and not done then
    done = true
    local ok, png = pcall(function() return emu.takeScreenshot() end)
    if ok and type(png) == "string" then
      local s = io.open(ROOT .. "script_screen.png", "wb")
      if s then s:write(png); s:close() end
    end
    local f = io.open(ROOT .. "script_trace.txt", "w")
    f:write(string.format("gate f%d-%d  bank $C7 reads=%d\n\n", GATE_FROM, GATE_TO, n))
    for _, s in ipairs(log) do f:write(s .. "\n") end
    f:close()
    emu.stop(0)
  end
end
emu.addEventCallback(onFrame, emu.eventType.endFrame)
